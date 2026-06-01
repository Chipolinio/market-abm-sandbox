# Назначение файла: проверить AnalyticsStore — SQL-метрики поверх Parquet (Slice 004 §4.4).
# Базовая идея: DuckDB read_parquet(glob), без pl.read_parquet в store-коде.
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import polars as pl
import pytest

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
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
    PRODUCTS_SCHEMA_DTYPES,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)


def _run_config(tmp_path: Path, *, run_id: str = "analytics-run") -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id=run_id
        ),
    )


def _persist_run(
    tmp_path: Path,
    *,
    run_id: str,
    ticks: list[tuple[pl.DataFrame, pl.DataFrame]],
) -> Path:
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
        n_ticks=len(ticks),
    )
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
    return ctx.run_root


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


def _products_snapshot(
  n: int,
  *,
  prices: list[float] | None = None,
) -> pl.DataFrame:
    prices = prices or [80.0] * n
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            "demand_index": [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col("demand_index").cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


def test_gmv_by_tick_aggregates(tmp_path: Path) -> None:
    tick0 = _tx_rows(
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
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 1,
                COL_SELLER_ID: 1,
                COL_PRICE_PAID: 50.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 30.0,
            },
        ]
    )
    tick1 = _tx_rows(
        [
            {
                COL_TICK_ID: 1,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 0,
                COL_SELLER_ID: 0,
                COL_PRICE_PAID: 200.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 180.0,
            },
        ]
    )
    run_root = _persist_run(
        tmp_path,
        run_id="gmv-run",
        ticks=[
            (tick0, _products_snapshot(2)),
            (tick1, _products_snapshot(2)),
        ],
    )
    store = AnalyticsStore(run_root)
    try:
        gmv = store.gmv_by_tick()
    finally:
        store.close()
    assert gmv.columns == [COL_TICK_ID, "gmv", "transaction_count"]
    by_tick = {row[COL_TICK_ID]: row for row in gmv.iter_rows(named=True)}
    assert by_tick[0]["gmv"] == pytest.approx(150.0)
    assert by_tick[0]["transaction_count"] == 2
    assert by_tick[1]["gmv"] == pytest.approx(200.0)
    assert by_tick[1]["transaction_count"] == 1


def test_gross_margin_by_seller(tmp_path: Path) -> None:
    tx = _tx_rows(
        [
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 0,
                COL_SELLER_ID: 0,
                COL_PRICE_PAID: 100.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 10.0,
            },
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 1,
                COL_SELLER_ID: 0,
                COL_PRICE_PAID: 50.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 30.0,
            },
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 2,
                COL_SELLER_ID: 1,
                COL_PRICE_PAID: 80.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 5.0,
            },
        ]
    )
    run_root = _persist_run(
        tmp_path,
        run_id="margin-run",
        ticks=[(tx, _products_snapshot(3))],
    )
    store = AnalyticsStore(run_root)
    try:
        margins = store.gross_margin_by_seller()
    finally:
        store.close()
    assert margins.columns == [
        COL_SELLER_ID,
        "total_gross_margin",
        "avg_gross_margin",
        "transaction_count",
    ]
    by_seller = {row[COL_SELLER_ID]: row for row in margins.iter_rows(named=True)}
    assert by_seller[0]["total_gross_margin"] == pytest.approx(40.0)
    assert by_seller[0]["avg_gross_margin"] == pytest.approx(20.0)
    assert by_seller[0]["transaction_count"] == 2
    assert by_seller[1]["total_gross_margin"] == pytest.approx(5.0)
    assert by_seller[1]["transaction_count"] == 1


def test_price_index_by_tick(tmp_path: Path) -> None:
    run_root = _persist_run(
        tmp_path,
        run_id="price-run",
        ticks=[
            (_tx_rows([]), _products_snapshot(2, prices=[100.0, 200.0])),
            (
                _tx_rows([]),
                _products_snapshot(2, prices=[110.0, 210.0]),
            ),
        ],
    )
    store = AnalyticsStore(run_root)
    try:
        index = store.price_index_by_tick()
    finally:
        store.close()
    assert index.columns == [
        COL_TICK_ID,
        "mean_price",
        "median_price",
        "p10_price",
        "p90_price",
    ]
    assert index[COL_TICK_ID].dtype == pl.Int32
    for col in ("mean_price", "median_price", "p10_price", "p90_price"):
        assert index[col].dtype == pl.Float64
    row0 = index.filter(pl.col(COL_TICK_ID) == 0).row(0, named=True)
    assert row0["mean_price"] == pytest.approx(150.0)
    row1 = index.filter(pl.col(COL_TICK_ID) == 1).row(0, named=True)
    assert row1["mean_price"] == pytest.approx(160.0)


def test_read_parquet_lazy_no_full_load(tmp_path: Path) -> None:
    tx = _tx_rows(
        [
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: 0,
                COL_LISTING_ID: 0,
                COL_SELLER_ID: 0,
                COL_PRICE_PAID: 10.0,
                COL_UNIT_COST: 1.0,
                COL_GROSS_MARGIN: 9.0,
            },
        ]
    )
    run_root = _persist_run(
        tmp_path, run_id="lazy-run", ticks=[(tx, _products_snapshot(1))]
    )

    def _forbid_read_parquet(*args: object, **kwargs: object) -> pl.DataFrame:
        raise AssertionError("pl.read_parquet must not be used in AnalyticsStore")

    store = AnalyticsStore(run_root)
    try:
        with patch.object(pl, "read_parquet", side_effect=_forbid_read_parquet):
            store.gmv_by_tick()
            store.gross_margin_by_seller()
            store.avg_price_by_listing_over_time()
            store.price_index_by_tick()
    finally:
        store.close()


def test_empty_run_gmv_schema(tmp_path: Path) -> None:
    empty_tx = _tx_rows([])
    run_root = _persist_run(
        tmp_path,
        run_id="empty-tx-run",
        ticks=[
            (empty_tx, _products_snapshot(1)),
            (empty_tx, _products_snapshot(1)),
        ],
    )
    store = AnalyticsStore(run_root)
    try:
        gmv = store.gmv_by_tick()
    finally:
        store.close()
    assert gmv.columns == [COL_TICK_ID, "gmv", "transaction_count"]
    assert gmv.height == 0


def test_price_index_null_on_empty_snapshot(tmp_path: Path) -> None:
    empty_products_schema = {
        name: getattr(pl, dtype) for name, dtype in PRODUCTS_SCHEMA_DTYPES.items()
    }
    empty_products = pl.DataFrame(
        {col: [] for col in PRODUCTS_COLUMNS}, schema=empty_products_schema
    )
    run_root = _persist_run(
        tmp_path,
        run_id="empty-snap-run",
        ticks=[
            (_tx_rows([]), _products_snapshot(1, prices=[50.0])),
            (_tx_rows([]), empty_products),
        ],
    )
    store = AnalyticsStore(run_root)
    try:
        index = store.price_index_by_tick()
    finally:
        store.close()
    assert index.height >= 1
    row0 = index.filter(pl.col(COL_TICK_ID) == 0)
    assert row0.height == 1
    assert row0["mean_price"][0] == pytest.approx(50.0)
    row1 = index.filter(pl.col(COL_TICK_ID) == 1)
    if row1.height == 1:
        assert row1["mean_price"][0] is None
        assert row1["median_price"][0] is None


def test_analytics_store_missing_run_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        AnalyticsStore(tmp_path / "nonexistent")
