# Назначение файла: TickStreamPayload с ticker_metrics и events (Slice 8.3).
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from market_abm.analytics.events import append_system_events, build_demand_shock_event
from market_abm.analytics.persist import open_duckdb_connection
from market_abm.analytics.store import AnalyticsStore
from market_abm.api.app import create_app
from market_abm.api.schemas.stream import TickStreamPayload
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.main import make_payload_fn
from tests.helpers.mini_run import build_mini_run


def _run_config(base_dir: Path) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(base_dir), run_id="default"),
    )


def test_ws_payload_includes_events_and_ticker() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp))
        event = build_demand_shock_event(
            run_id="default",
            tick_id=0,
            seq=0,
            pct_drop=30.0,
        )
        con = open_duckdb_connection(_run_config(Path(tmp)).persistence)
        try:
            append_system_events(run_root, __import__("polars").DataFrame([event]), con)
        finally:
            con.close()

        store = AnalyticsStore(run_root)
        try:
            payload = make_payload_fn(store)(0)
        finally:
            store.close()

    assert payload.ticker_metrics is not None
    assert payload.ticker_metrics.current_tick == 0
    assert payload.ticker_metrics.total_market_gmv > 0
    assert len(payload.events) >= 1
    assert payload.events[0].display_code == "DEMAND_SHOCK"


def test_get_system_events_rest_backfill() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp))
        import polars as pl

        events = [
            build_demand_shock_event(run_id="default", tick_id=5, seq=0, pct_drop=10.0),
            build_demand_shock_event(run_id="default", tick_id=10, seq=1, pct_drop=20.0),
        ]
        con = open_duckdb_connection(_run_config(Path(tmp)).persistence)
        try:
            append_system_events(run_root, pl.DataFrame(events), con)
        finally:
            con.close()

        store = AnalyticsStore(run_root)
        app = create_app(worker=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock())
        app.state.analytics_store = store
        client = TestClient(app)

        resp = client.get("/api/v1/analytics/system-events?limit=10")
        assert resp.status_code == 200
        body = resp.json()
        tick_ids = [e["tick_id"] for e in body["events"]]
        assert tick_ids == sorted(tick_ids, reverse=True)
        store.close()


def test_market_leaders_sorted_by_working_capital() -> None:
    import polars as pl

    from market_abm.analytics.leaders import query_market_leaders, write_sellers_state_snapshot
    from market_abm.domain.constants import COL_IS_BANKRUPT, COL_SELLER_ID, COL_WORKING_CAPITAL

    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp))
        sellers_state = pl.DataFrame(
            {
                COL_SELLER_ID: [0, 1, 2],
                COL_WORKING_CAPITAL: [500.0, 1000.0, 300.0],
                COL_IS_BANKRUPT: [False, False, False],
            }
        ).with_columns(
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
            pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
        )
        write_sellers_state_snapshot(run_root, tick_id=0, sellers_state_df=sellers_state)

        store = AnalyticsStore(run_root)
        try:
            raw = query_market_leaders(store, tick_id=0, limit=5)
        finally:
            store.close()

    capitals = [leader["working_capital"] for leader in raw["leaders"]]
    assert capitals == sorted(capitals, reverse=True)
    assert raw["leaders"][0]["seller_id"] == 1


def test_tick_stream_payload_schema_accepts_new_fields() -> None:
    raw = {
        "tick_id": 1,
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "market_summary": {
            "mean_price": 1.0,
            "total_gmv": 2.0,
            "total_transactions": 3,
            "price_quantiles": None,
        },
        "ticker_metrics": {
            "active_sellers_count": 1,
            "total_non_bankrupt_sellers": 2,
            "total_market_gmv": 100.0,
            "market_price_index": 1.0,
            "current_tick": 1,
        },
        "active_drift_alerts": [],
        "events": [],
        "worker_state": "IDLE",
    }
    payload = TickStreamPayload.model_validate(raw)
    assert payload.ticker_metrics is not None
    assert payload.events == []
