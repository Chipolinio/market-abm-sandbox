# Мини-прогон с Parquet для e2e/docker smoke (Spec 007 §10.3).
from __future__ import annotations

from pathlib import Path

import polars as pl

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
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
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings


def _run_config(base_dir: Path, *, run_id: str = "default") -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(base_dir), run_id=run_id),
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


def build_mini_run(base_dir: Path, *, run_id: str = "default") -> Path:
    """
    Создаёт run_root с manifest, reference snapshots и tick_0 parquet.
    base_dir — родитель run_id (для Docker: /data/runs → run_root = base_dir/default).
    """
    config = _run_config(base_dir, run_id=run_id)
    buyers = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=30, seed=1))
    sellers = generate_sellers(SellerPopulationConfig.default_market(n_sellers=9, seed=1))
    listings = initialize_listings(
        sellers,
        __import__("market_abm.config.repricing", fromlist=["ListingInitConfig"]).ListingInitConfig.default_market(),
        seed=1,
    )
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=1,
    )
    rich_buyer = int(
        buyers.filter(pl.col("pvd_segment").cast(pl.String) == "rich")[COL_BUYER_ID][0]
    )
    low_buyer = int(
        buyers.filter(pl.col("pvd_segment").cast(pl.String) == "low")[COL_BUYER_ID][0]
    )
    max_profit_seller = int(
        sellers.filter(pl.col("strategy_type").cast(pl.String) == "MaxProfit")[COL_SELLER_ID][0]
    )
    max_volume_seller = int(
        sellers.filter(pl.col("strategy_type").cast(pl.String) == "MaxVolume")[COL_SELLER_ID][0]
    )

    tx = _tx_rows(
        [
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: rich_buyer,
                COL_LISTING_ID: max_profit_seller,
                COL_SELLER_ID: max_profit_seller,
                COL_PRICE_PAID: 100.0,
                COL_UNIT_COST: 20.0,
                COL_GROSS_MARGIN: 80.0,
            },
            {
                COL_TICK_ID: 0,
                COL_BUYER_ID: low_buyer,
                COL_LISTING_ID: max_volume_seller,
                COL_SELLER_ID: max_volume_seller,
                COL_PRICE_PAID: 50.0,
                COL_UNIT_COST: 10.0,
                COL_GROSS_MARGIN: 40.0,
            },
        ]
    )
    products = _products_snapshot(9, prices=[100.0, 200.0] + [80.0] * 7)
    con = open_duckdb_connection(config.persistence)
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=tx,
            products_df=products,
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()
    return ctx.run_root


def open_mini_run_store(run_root: Path) -> AnalyticsStore:
    return AnalyticsStore(run_root)
