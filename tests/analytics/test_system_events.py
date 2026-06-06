# Назначение файла: детектор system_events и persist (Slice 8.3).
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import polars as pl
import pytest

from market_abm.analytics.events import (
    append_system_events,
    build_bankruptcy_event,
    build_demand_shock_event,
    coalesce_bankruptcy_events,
    detect_system_events,
)
from market_abm.analytics.persist import open_duckdb_connection
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.events import (
    CollusionDetectorConfig,
    FlashCrashDetectorConfig,
    SystemEventsConfig,
)
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
    PRODUCTS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)
from market_abm.domain.events import (
    COL_DISPLAY_CODE,
    COL_EVENT_ID,
    COL_EVENT_TYPE,
    COL_MESSAGE,
    COL_PAYLOAD_JSON,
    COL_SEVERITY,
    SystemEventType,
)
from market_abm.domain.shocks import ShockType
from tests.analytics.test_analytics_store import _persist_run, _products_snapshot, _tx_rows


def _run_config(tmp_path: Path) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id="events-run"
        ),
    )


def _correlated_collusion_ticks(n_ticks: int = 20) -> list[tuple[pl.DataFrame, pl.DataFrame]]:
    """Seller 0 и 1 — синхронные цены; seller 2 — независимый ряд."""
    ticks: list[tuple[pl.DataFrame, pl.DataFrame]] = []
    for t in range(n_ticks):
        base = 100.0 + t * 0.5
        products = _products_snapshot(
            3,
            prices=[base, base + 0.1, 200.0 - t * 3.0],
        )
        ticks.append((_tx_rows([]), products))
    return ticks


def _flash_crash_ticks() -> list[tuple[pl.DataFrame, pl.DataFrame]]:
    ticks: list[tuple[pl.DataFrame, pl.DataFrame]] = []
    for t in range(15):
        price = 100.0 if t < 10 else 50.0
        products = _products_snapshot(2, prices=[price, price])
        ticks.append((_tx_rows([]), products))
    return ticks


def test_detect_collusion_high_correlation(tmp_path: Path) -> None:
    run_root = _persist_run(tmp_path, run_id="events-run", ticks=_correlated_collusion_ticks())
    store = AnalyticsStore(run_root)
    try:
        config = SystemEventsConfig(
            collusion=CollusionDetectorConfig(
                window_ticks=20,
                min_correlation=0.9,
                min_observations=15,
            )
        )
        events = detect_system_events(store, as_of_tick=19, config=config, run_id="events-run")
    finally:
        store.close()

    assert events.height >= 1
    row = events.filter(pl.col(COL_DISPLAY_CODE) == "PRICING_WAR").row(0, named=True)
    assert row[COL_EVENT_TYPE] == SystemEventType.COLLUSION_DETECTED.value
    assert "dumping loop" in row[COL_MESSAGE]


def test_detect_collusion_low_correlation_silent(tmp_path: Path) -> None:
    ticks = []
    for t in range(20):
        products = _products_snapshot(2, prices=[100.0 + t, 200.0 - t * 2])
        ticks.append((_tx_rows([]), products))
    run_root = _persist_run(tmp_path, run_id="events-run", ticks=ticks)
    store = AnalyticsStore(run_root)
    try:
        config = SystemEventsConfig(
            collusion=CollusionDetectorConfig(min_correlation=0.99, min_observations=15)
        )
        events = detect_system_events(store, as_of_tick=19, config=config, run_id="events-run")
    finally:
        store.close()

    assert events.height == 0


def test_detect_flash_crash_40pct_drop(tmp_path: Path) -> None:
    run_root = _persist_run(tmp_path, run_id="events-run", ticks=_flash_crash_ticks())
    store = AnalyticsStore(run_root)
    try:
        config = SystemEventsConfig(
            flash_crash=FlashCrashDetectorConfig(window_ticks=5, median_drop_pct=0.40)
        )
        events = detect_system_events(store, as_of_tick=14, config=config, run_id="events-run")
    finally:
        store.close()

    assert events.height >= 1
    row = events.filter(pl.col(COL_EVENT_TYPE) == SystemEventType.FLASH_CRASH.value).row(
        0, named=True
    )
    assert row[COL_DISPLAY_CODE] == "FLASH_CRASH"
    assert row[COL_SEVERITY] == "critical"


def test_append_system_events_readable(tmp_path: Path) -> None:
    run_root = _persist_run(tmp_path, run_id="events-run", ticks=_correlated_collusion_ticks(5))
    event = build_demand_shock_event(
        run_id="events-run",
        tick_id=3,
        seq=0,
        pct_drop=30.0,
        shock_type=ShockType.DEMAND_CRASH,
    )
    events_df = pl.DataFrame([event])
    con = open_duckdb_connection(_run_config(tmp_path).persistence)
    try:
        append_system_events(run_root, events_df, con)
    finally:
        con.close()

    store = AnalyticsStore(run_root)
    try:
        rows = store.recent_system_events(limit=10)
    finally:
        store.close()

    assert len(rows) == 1
    assert rows[0]["display_code"] == "DEMAND_SHOCK"
    assert rows[0]["tick_id"] == 3


def test_append_system_events_merges_existing_file(tmp_path: Path) -> None:
    """Два append подряд (cmd + detector на одном тике) не ломают merge."""
    run_root = tmp_path / "events-run"
    (run_root / "system_events").mkdir(parents=True)
    con = open_duckdb_connection(_run_config(tmp_path).persistence)
    try:
        first = build_demand_shock_event(
            run_id="events-run",
            tick_id=0,
            seq=0,
            pct_drop=10.0,
            shock_type=ShockType.DEMAND_CRASH,
        )
        append_system_events(run_root, pl.DataFrame([first]), con)
        second = build_demand_shock_event(
            run_id="events-run",
            tick_id=0,
            seq=1,
            pct_drop=20.0,
            shock_type=ShockType.DEMAND_BOOM,
        )
        append_system_events(run_root, pl.DataFrame([second]), con)
    finally:
        con.close()

    fragments = sorted((run_root / "system_events").glob("evt_*.parquet"))
    assert len(fragments) == 2
    row_count = duckdb.sql(
        "SELECT COUNT(*) FROM read_parquet(?)",
        params=[str(run_root / "system_events" / "evt_*.parquet")],
    ).fetchone()[0]
    assert row_count == 2


def test_demand_shock_emits_system_event() -> None:
    event = build_demand_shock_event(
        run_id="r1",
        tick_id=12,
        seq=0,
        pct_drop=30.0,
        shock_type=ShockType.DEMAND_CRASH,
    )
    assert event[COL_DISPLAY_CODE] == "DEMAND_SHOCK"
    assert event[COL_EVENT_TYPE] == SystemEventType.DEMAND_SHOCK.value
    assert "30" in event[COL_MESSAGE]


def test_bankruptcy_emits_system_event() -> None:
    event = build_bankruptcy_event(run_id="r1", tick_id=87, seller_id=3, seq=0)
    assert event[COL_DISPLAY_CODE] == "BANKRUPTCY"
    assert event[COL_EVENT_TYPE] == SystemEventType.BANKRUPTCY.value
    assert "Seller_3" in event[COL_MESSAGE]


def test_coalesce_bankruptcy_events_groups_routine_mass_exit() -> None:
    events, seq = coalesce_bankruptcy_events(
        run_id="r1",
        tick_id=1,
        bankrupt_seller_ids=[3, 22, 25, 28, 30, 31],
        top_seller_ids=frozenset({3}),
        seq_start=0,
    )
    assert seq == 2
    assert len(events) == 2
    assert "Seller_3" in events[0][COL_MESSAGE]
    assert "массово выбыло 5 селлеров" in events[1][COL_MESSAGE]
    payload = json.loads(str(events[1][COL_PAYLOAD_JSON]))
    assert payload["aggregated"] is True
    assert payload["count"] == 5
