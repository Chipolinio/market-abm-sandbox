# Назначение файла: проверить DuckDB/Parquet persistence и run_simulation_and_persist (Slice 004 §4.3).
# Базовая идея: append тика на диск через Arrow-bridge; ленивая запись при итерации генератора.
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import duckdb
import polars as pl
import pytest

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
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)
from market_abm.analytics.persist import (
    SimulationRunContext,
    init_run_directory,
    persist_tick_artifacts,
    resolve_run_id,
)
from market_abm.config.repricing import RepricingConfig
from market_abm.simulation.runner import run_simulation_and_persist


def _persistence(tmp_path: Path, *, run_id: str = "test-run") -> PersistenceConfig:
    return PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id)


def _run_config(tmp_path: Path, *, run_id: str = "test-run", seed: int = 1) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=5,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
        persistence=_persistence(tmp_path, run_id=run_id),
    )


def _buyers(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            "budget": [500.0] * n,
            "beta_price": [-0.2] * n,
            "beta_delivery": [-0.3] * n,
            "beta_rating": [-0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            "purchase_frequency": [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col("budget").cast(pl.Float32),
        pl.col("beta_price").cast(pl.Float32),
        pl.col("beta_delivery").cast(pl.Float32),
        pl.col("beta_rating").cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col("purchase_frequency").cast(pl.Float32),
    )


def _sellers(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            "strategy_type": ["MaxProfit"] * n,
            "capital": [100.0] * n,
            "margin_floor": [0.2] * n,
            "repricing_speed": [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col("strategy_type").cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col("margin_floor").cast(pl.Float32),
        pl.col("repricing_speed").cast(pl.UInt8),
    )


def _listings(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: [80.0] * n,
            "demand_index": [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col("demand_index").cast(pl.Float32),
    )


def _products(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: [80.0] * n,
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
    )


def _transactions_row(*, tick_id: int = 0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_TICK_ID: [tick_id],
            COL_BUYER_ID: [0],
            COL_LISTING_ID: [0],
            COL_SELLER_ID: [0],
            COL_PRICE_PAID: [80.0],
            COL_UNIT_COST: [20.0],
            COL_GROSS_MARGIN: [60.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )


def _empty_transactions() -> pl.DataFrame:
    schema = {
        name: getattr(pl, dtype) for name, dtype in TRANSACTIONS_SCHEMA_DTYPES.items()
    }
    return pl.DataFrame({col: [] for col in TRANSACTIONS_COLUMNS}, schema=schema)


def _count_tick_parquets(directory: Path) -> int:
    return len(list(directory.glob("tick_*.parquet")))


def test_init_run_directory_layout(tmp_path: Path) -> None:
    buyers = _buyers(10)
    sellers = _sellers(4)
    listings = _listings(4)
    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-a",
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=5,
    )
    assert isinstance(ctx, SimulationRunContext)
    assert ctx.run_root == tmp_path / "run-a"
    assert (ctx.run_root / "transactions").is_dir()
    assert (ctx.run_root / "products_snapshots").is_dir()
    manifest_path = ctx.run_root / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == "run-a"
    assert manifest["n_ticks"] == 5
    assert manifest["n_buyers"] == 10
    assert manifest["n_sellers"] == 4
    assert manifest["n_listings"] == 4
    assert manifest["engine"] == "numpy_softmax"
    assert "config_hash" in manifest


def test_persist_tick_writes_parquet_files(tmp_path: Path) -> None:
    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-b",
        buyers_df=_buyers(2),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=1,
    )
    con = duckdb.connect()
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=_transactions_row(),
            products_df=_products(1),
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()
    tx_path = ctx.run_root / "transactions" / "tick_000000.parquet"
    prod_path = ctx.run_root / "products_snapshots" / "tick_000000.parquet"
    assert tx_path.is_file()
    assert prod_path.is_file()
    reader = duckdb.connect()
    try:
        tx_count = reader.execute(
            f"SELECT COUNT(*) FROM read_parquet('{tx_path}')"
        ).fetchone()[0]
        prod_count = reader.execute(
            f"SELECT COUNT(*) FROM read_parquet('{prod_path}')"
        ).fetchone()[0]
    finally:
        reader.close()
    assert tx_count == 1
    assert prod_count == 1


def test_persist_tick_schema_roundtrip(tmp_path: Path) -> None:
    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-c",
        buyers_df=_buyers(1),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=1,
    )
    con = duckdb.connect()
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=_transactions_row(),
            products_df=_products(1),
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()
    tx_df = pl.read_parquet(ctx.run_root / "transactions" / "tick_000000.parquet")
    prod_df = pl.read_parquet(ctx.run_root / "products_snapshots" / "tick_000000.parquet")
    assert tx_df.columns == list(TRANSACTIONS_COLUMNS)
    assert prod_df.columns == list(PRODUCTS_COLUMNS)


def test_persist_duplicate_tick_raises(tmp_path: Path) -> None:
    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-d",
        buyers_df=_buyers(1),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=2,
    )
    con = duckdb.connect()
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=_transactions_row(),
            products_df=_products(1),
            config=config.persistence,
            con=con,
        )
        with pytest.raises(FileExistsError):
            persist_tick_artifacts(
                ctx.run_root,
                tick_id=0,
                transactions_df=_transactions_row(),
                products_df=_products(1),
                config=config.persistence,
                con=con,
            )
    finally:
        con.close()


def test_persist_empty_transactions(tmp_path: Path) -> None:
    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-e",
        buyers_df=_buyers(1),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=1,
    )
    con = duckdb.connect()
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=_empty_transactions(),
            products_df=_products(1),
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()
    tx_df = pl.read_parquet(ctx.run_root / "transactions" / "tick_000000.parquet")
    assert tx_df.height == 0
    assert tx_df.columns == list(TRANSACTIONS_COLUMNS)


def test_run_simulation_and_persist_lazy_persist(tmp_path: Path) -> None:
    config = _run_config(tmp_path, run_id="run-f", seed=42)
    gen = run_simulation_and_persist(
        _buyers(8),
        _sellers(2),
        _listings(2),
        n_ticks=10,
        config=config,
    )
    run_root = tmp_path / "run-f"
    assert (run_root / "manifest.json").is_file()
    assert _count_tick_parquets(run_root / "transactions") == 0
    assert _count_tick_parquets(run_root / "products_snapshots") == 0
    list(gen)
    assert _count_tick_parquets(run_root / "transactions") == 10
    assert _count_tick_parquets(run_root / "products_snapshots") == 10


def test_run_simulation_and_persist_partial_iteration(tmp_path: Path) -> None:
    config = _run_config(tmp_path, run_id="run-g", seed=7)
    gen = run_simulation_and_persist(
        _buyers(6),
        _sellers(2),
        _listings(2),
        n_ticks=10,
        config=config,
    )
    run_root = tmp_path / "run-g"
    for _ in range(3):
        next(gen)
    assert _count_tick_parquets(run_root / "transactions") == 3
    assert _count_tick_parquets(run_root / "products_snapshots") == 3


def test_resolve_run_id_does_not_mutate_config() -> None:
    persistence = PersistenceConfig(run_id=None)
    before = persistence.model_dump()
    id_a = resolve_run_id(persistence)
    id_b = resolve_run_id(persistence)
    assert id_a != id_b
    assert persistence.model_dump() == before


def test_init_returns_simulation_run_context(tmp_path: Path) -> None:
    config = _run_config(tmp_path, run_id="fixed-id")
    ctx = init_run_directory(
        config,
        run_id="fixed-id",
        buyers_df=_buyers(1),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=2,
    )
    assert ctx.run_id == "fixed-id"
    assert ctx.run_root == tmp_path / "fixed-id"


def test_persist_uses_arrow_bridge(tmp_path: Path) -> None:
    import pyarrow as pa

    config = _run_config(tmp_path)
    ctx = init_run_directory(
        config,
        run_id="run-h",
        buyers_df=_buyers(1),
        sellers_df=_sellers(1),
        listings_df=_listings(1),
        n_ticks=1,
    )
    tx = _transactions_row()
    products = _products(1)
    con = duckdb.connect()
    registered: list[type] = []
    original_register = duckdb.DuckDBPyConnection.register

    def _spy_register(self: duckdb.DuckDBPyConnection, name: str, value: object) -> None:
        registered.append(type(value))
        original_register(self, name, value)

    with patch.object(duckdb.DuckDBPyConnection, "register", _spy_register):
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=tx,
            products_df=products,
            config=config.persistence,
            con=con,
        )
    con.close()
    assert len(registered) == 2
    assert pl.DataFrame not in registered
    assert all(t is pa.Table for t in registered)
