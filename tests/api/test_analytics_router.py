# Тесты Analytics REST API и health (Slice 7.1).
# Стратегия: TestClient + инжектированный AnalyticsStore на app.state.
from __future__ import annotations

import json
import multiprocessing as mp
from pathlib import Path
from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi.testclient import TestClient

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.api.app import create_app
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
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
    PRODUCTS_SCHEMA_DTYPES,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)
from market_abm.worker.process import WorkerState


def _run_config(tmp_path: Path, *, run_id: str = "api-analytics-run") -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id=run_id
        ),
    )


def _tx_rows(rows: list[dict]) -> pl.DataFrame:
    if not rows:
        schema = {
            name: getattr(pl, dtype) for name, dtype in TRANSACTIONS_SCHEMA_DTYPES.items()
        }
        return pl.DataFrame({col: [] for col in TRANSACTIONS_COLUMNS}, schema=schema)
    return pl.DataFrame(rows).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )


def _products_snapshot(n: int, *, prices: list[float] | None = None) -> pl.DataFrame:
    prices = prices or [80.0] * n
    schema = {name: getattr(pl, dtype) for name, dtype in PRODUCTS_SCHEMA_DTYPES.items()}
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            "demand_index": [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        },
        schema=schema,
    )


def _persist_mini_run(tmp_path: Path) -> AnalyticsStore:
    run_id = "api-analytics-run"
    config = _run_config(tmp_path, run_id=run_id)
    buyers = pl.DataFrame({COL_BUYER_ID: [0]}).with_columns(pl.col(COL_BUYER_ID).cast(pl.Int32))
    sellers = pl.DataFrame({COL_SELLER_ID: [0, 1]}).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32)
    )
    listings = pl.DataFrame({COL_LISTING_ID: [0, 1], COL_SELLER_ID: [0, 1]}).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
    )
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=2,
    )
    ticks = [
        (
            _tx_rows(
                [
                    {
                        COL_TICK_ID: 0,
                        COL_BUYER_ID: 0,
                        COL_LISTING_ID: 0,
                        COL_SELLER_ID: 0,
                        COL_PRICE_PAID: 100.0,
                        COL_UNIT_COST: 20.0,
                        COL_GROSS_MARGIN: 80.0,
                    },
                ]
            ),
            _products_snapshot(2, prices=[100.0, 200.0]),
        ),
        (
            _tx_rows(
                [
                    {
                        COL_TICK_ID: 1,
                        COL_BUYER_ID: 0,
                        COL_LISTING_ID: 1,
                        COL_SELLER_ID: 1,
                        COL_PRICE_PAID: 50.0,
                        COL_UNIT_COST: 20.0,
                        COL_GROSS_MARGIN: 30.0,
                    },
                ]
            ),
            _products_snapshot(2, prices=[110.0, 210.0]),
        ),
    ]
    con = open_duckdb_connection(config.persistence)
    try:
        for tick_id, (tx, products) in enumerate(ticks):
            persist_tick_artifacts(
                ctx.run_root,
                tick_id=tick_id,
                transactions_df=tx,
                products_df=products,
                config=config.persistence,
                con=con,
            )
    finally:
        con.close()
    return AnalyticsStore(ctx.run_root)


def _make_mock_worker() -> MagicMock:
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.tick_counter = mp.Value("i", 0)
    worker.state = WorkerState.IDLE
    worker.last_error = None
    worker.run_id = "api-analytics-run"
    return worker


def _make_client(store: AnalyticsStore | None = None) -> TestClient:
    return TestClient(
        create_app(worker=_make_mock_worker(), analytics_store=store),
        raise_server_exceptions=True,
    )


def test_health_endpoint_returns_ok() -> None:
    client = _make_client()
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_price_index_endpoint_returns_sorted_points(tmp_path: Path) -> None:
    store = _persist_mini_run(tmp_path)
    try:
        client = _make_client(store)
        response = client.get("/api/v1/analytics/price-index")
    finally:
        store.close()

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == "api-analytics-run"
    points = body["points"]
    assert len(points) == 2
    tick_ids = [p["tick_id"] for p in points]
    assert tick_ids == sorted(tick_ids)
    assert points[0]["mean_price"] == pytest.approx(150.0, rel=0.02)
    assert points[0]["p50"] == pytest.approx(150.0, rel=0.02)


def test_gmv_by_tick_endpoint_returns_gmv(tmp_path: Path) -> None:
    store = _persist_mini_run(tmp_path)
    try:
        client = _make_client(store)
        response = client.get("/api/v1/analytics/gmv-by-tick")
    finally:
        store.close()

    assert response.status_code == 200
    points = response.json()["points"]
    by_tick = {p["tick_id"]: p for p in points}
    assert by_tick[0]["gmv"] == pytest.approx(100.0)
    assert by_tick[0]["transaction_count"] == 1
    assert by_tick[1]["gmv"] == pytest.approx(50.0)


def test_price_index_empty_run_when_no_store() -> None:
    client = _make_client(None)
    response = client.get("/api/v1/analytics/price-index")
    assert response.status_code == 200
    assert response.json()["points"] == []


def test_market_summary_single_tick(tmp_path: Path) -> None:
    store = _persist_mini_run(tmp_path)
    try:
        client = _make_client(store)
        response = client.get("/api/v1/analytics/market-summary", params={"tick_id": 0})
    finally:
        store.close()

    assert response.status_code == 200
    body = response.json()
    assert body["total_gmv"] == pytest.approx(100.0)
    assert body["total_transactions"] == 1
    assert body["mean_price"] == pytest.approx(150.0, rel=0.02)
    assert body["price_quantiles"] is not None
    assert body["price_quantiles"]["p10"] is not None
    assert body["price_quantiles"]["p50"] is not None
    assert body["price_quantiles"]["p90"] is not None


def test_ws_payload_includes_price_quantiles(tmp_path: Path) -> None:
    from market_abm.main import make_payload_fn

    store = _persist_mini_run(tmp_path)
    try:
        payload_fn = make_payload_fn(store)
        payload = payload_fn(0)
    finally:
        store.close()

    dumped = json.loads(payload.model_dump_json())
    quantiles = dumped["market_summary"]["price_quantiles"]
    assert quantiles is not None
    assert "p10" in quantiles
    assert "p50" in quantiles
    assert "p90" in quantiles


def test_price_index_uses_approx_quantile() -> None:
    import inspect

    from market_abm.analytics import store as store_mod

    source = inspect.getsource(store_mod)
    assert "approx_quantile" in source
    assert "MEDIAN(price)" not in source
    assert "quantile_cont(price" not in source


def test_top_listings_endpoint_returns_ranked_series(tmp_path: Path) -> None:
    store = _persist_mini_run(tmp_path)
    try:
        client = _make_client(store)
        response = client.get("/api/v1/analytics/top-listings", params={"limit": 10})
    finally:
        store.close()

    assert response.status_code == 200
    body = response.json()
    listings = body["listings"]
    assert len(listings) == 2
    assert listings[0]["listing_id"] == 0
    assert listings[1]["listing_id"] == 1
    tick0 = listings[0]["points"][0]
    assert tick0["tick_id"] == 0
    assert tick0["gmv"] == pytest.approx(100.0)
    assert tick0["volume"] == 1
    assert tick0["price"] == pytest.approx(100.0, rel=0.02)


def test_top_listings_empty_when_no_store() -> None:
    client = _make_client(None)
    response = client.get("/api/v1/analytics/top-listings")
    assert response.status_code == 200
    assert response.json()["listings"] == []


def test_top_listings_limit_validation() -> None:
    client = _make_client(None)
    response = client.get("/api/v1/analytics/top-listings", params={"limit": 11})
    assert response.status_code == 422
