# Slice A.1 — population params: pending_session → worker → manifest.json
# L1: pure helpers (_worker_n_buyers/_worker_n_sellers)
# L2: LiveSimulationSession bootstrap + manifest contract
from __future__ import annotations

import json
import queue
from pathlib import Path

import polars as pl
import pytest

from market_abm.worker.simulation_session import (
    LiveSimulationSession,
    _worker_n_buyers,
    _worker_n_sellers,
)
from tests.worker.conftest import read_manifest, write_pending_session


# ---------------------------------------------------------------------------
# L1 — pure helpers (без HTTP, без mp.spawn)
# ---------------------------------------------------------------------------


def test_a1_l1_t1_pending_overlay_overrides_env_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """pending_session.json приоритетнее WORKER_N_BUYERS env."""
    monkeypatch.setenv("WORKER_N_BUYERS", "999")
    monkeypatch.setenv("WORKER_N_SELLERS", "99")
    write_pending_session(tmp_path, {"n_buyers": 100, "n_sellers": 20})

    assert _worker_n_buyers(tmp_path) == 100
    assert _worker_n_sellers(tmp_path) == 20


def test_a1_l1_t2_worker_n_sellers_reads_pending_session(tmp_path: Path) -> None:
    write_pending_session(tmp_path, {"n_sellers": 20})

    assert _worker_n_sellers(tmp_path) == 20


def test_a1_l1_t3_worker_population_defaults_without_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_N_BUYERS", raising=False)
    monkeypatch.delenv("WORKER_N_SELLERS", raising=False)

    assert _worker_n_buyers(tmp_path) == 300
    assert _worker_n_sellers(tmp_path) == 30


def test_a1_l1_t4_worker_n_buyers_reads_pending_session(tmp_path: Path) -> None:
    write_pending_session(tmp_path, {"n_buyers": 100})

    assert _worker_n_buyers(tmp_path) == 100


# ---------------------------------------------------------------------------
# L2 — LiveSimulationSession → manifest.json
# ---------------------------------------------------------------------------


def _run_first_tick(tmp_path: Path, pending: dict[str, object] | None = None) -> LiveSimulationSession:
    if pending is not None:
        write_pending_session(tmp_path, pending)
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)
    session.run_tick(0)
    return session


def test_a1_l2_t1_live_session_manifest_reflects_pending_n_buyers_and_sellers(
    tmp_path: Path,
) -> None:
    session = _run_first_tick(
        tmp_path,
        {"n_buyers": 100, "n_sellers": 20, "seed": 42},
    )
    try:
        manifest = read_manifest(tmp_path)
        assert manifest["n_buyers"] == 100
        assert manifest["n_sellers"] == 20
        assert manifest["seed"] == 42
    finally:
        session.close()


def test_a1_l2_t2_start_request_population_size(tmp_path: Path) -> None:
    """Якорный acceptance: n_buyers=100 из pending → manifest n_buyers==100."""
    session = _run_first_tick(tmp_path, {"n_buyers": 100, "n_sellers": 15})
    try:
        manifest = read_manifest(tmp_path)
        assert manifest["n_buyers"] == 100
    finally:
        session.close()


def test_a1_l2_t3_configure_overlay_manifest_reflects_slider_n_buyers(tmp_path: Path) -> None:
    """
    Контракт фронта: POST /configure (слайдер n_buyers) → pending без n_sellers.
    После POST /start({force_clear}) merge добавляет n_sellers default.
    """
    session = _run_first_tick(
        tmp_path,
        {
            "n_buyers": 8_000,
            "seller_mix": {
                "catboost_pct": 0.4,
                "rule_based_pct": 0.35,
                "basic_pct": 0.25,
            },
            "n_sellers": 50,
        },
    )
    try:
        manifest = read_manifest(tmp_path)
        assert manifest["n_buyers"] == 8_000
        assert manifest["n_sellers"] == 50
    finally:
        session.close()


def test_a1_l2_t4_manifest_n_buyers_matches_transaction_buyer_universe(
    tmp_path: Path,
) -> None:
    """manifest.n_buyers согласован с фактической популяцией (buyer_id < n_buyers)."""
    session = _run_first_tick(tmp_path, {"n_buyers": 100, "n_sellers": 15})
    try:
        manifest = read_manifest(tmp_path)
        tx = pl.read_parquet(tmp_path / "transactions" / "tick_000000.parquet")
        assert manifest["n_buyers"] == 100
        if tx.height > 0:
            assert int(tx["buyer_id"].max()) < 100
    finally:
        session.close()


def test_a1_l2_t5_buyers_batch_size_floors_at_101_when_n_buyers_is_100(
    tmp_path: Path,
) -> None:
    """ChoiceModelConfig: buyers_batch_size gt=100 → min(max(n, 101), 300)."""
    session = _run_first_tick(tmp_path, {"n_buyers": 100, "n_sellers": 10})
    try:
        assert session._config.choice.buyers_batch_size == 101
    finally:
        session.close()


def test_a1_l2_t6_pending_session_consumed_after_bootstrap(tmp_path: Path) -> None:
    session = _run_first_tick(tmp_path, {"n_buyers": 250})
    try:
        assert not (tmp_path / "pending_session.json").is_file()
    finally:
        session.close()


def test_a1_l2_t7_manifest_contains_analytics_fields(tmp_path: Path) -> None:
    session = _run_first_tick(tmp_path, {"n_buyers": 200, "n_sellers": 25, "seed": 7})
    try:
        manifest = read_manifest(tmp_path)
        for key in ("run_id", "n_buyers", "n_sellers", "config_hash", "engine", "seed"):
            assert key in manifest
        assert manifest["engine"] == "numpy_softmax"
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Regression guards (не L1/L2, но защищают смежные инварианты A.1)
# ---------------------------------------------------------------------------


def test_live_session_emits_tick_pulse_from_tick_zero(tmp_path: Path) -> None:
    session = _run_first_tick(tmp_path, {"n_buyers": 100, "n_sellers": 10})
    try:
        from market_abm.analytics.store import AnalyticsStore

        store = AnalyticsStore(tmp_path)
        rows = store.recent_system_events(limit=10)
        store.close()
        pulse = [r for r in rows if r["display_code"] == "TICK_PULSE"]
        assert len(pulse) >= 1
        assert pulse[0]["tick_id"] == 0
    finally:
        session.close()


def test_live_session_produces_positive_gmv_on_first_tick(tmp_path: Path) -> None:
    session = _run_first_tick(tmp_path, {"n_buyers": 300, "n_sellers": 30})
    try:
        tx_path = tmp_path / "transactions" / "tick_000000.parquet"
        assert tx_path.is_file()
        tx = pl.read_parquet(tx_path)
        assert tx.height > 0
        assert float(tx["price_paid"].sum()) > 0.0
    finally:
        session.close()
