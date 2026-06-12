# Demand matrix: strategy_type × pvd_segment transaction heatmap.
from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl

from market_abm.analytics.leaders import query_demand_matrix
from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
    DEMAND_MATRIX_PVD_ORDER,
    DEMAND_MATRIX_STRATEGY_ORDER,
    TRANSACTIONS_COLUMNS,
)
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings


def _build_run_with_transactions(tmp: Path) -> Path:
    config = SimulationRunConfig(
        seed=7,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp), run_id="dm"),
    )
    buyers = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=30, seed=7))
    sellers = generate_sellers(SellerPopulationConfig.default_market(n_sellers=9, seed=7))
    listings = initialize_listings(sellers, ListingInitConfig.default_market(), seed=7)
    ctx = init_run_directory(
        config,
        run_id="dm",
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=10,
    )

    rich_buyer = int(buyers.filter(pl.col("pvd_segment").cast(pl.String) == "rich")[COL_BUYER_ID][0])
    low_buyer = int(buyers.filter(pl.col("pvd_segment").cast(pl.String) == "low")[COL_BUYER_ID][0])
    max_profit = int(sellers.filter(pl.col("strategy_type").cast(pl.String) == "MaxProfit")[COL_SELLER_ID][0])
    max_volume = int(sellers.filter(pl.col("strategy_type").cast(pl.String) == "MaxVolume")[COL_SELLER_ID][0])

    tx = pl.DataFrame(
        {
            COL_TICK_ID: [0, 0, 0],
            COL_BUYER_ID: [rich_buyer, rich_buyer, low_buyer],
            COL_LISTING_ID: [max_profit, max_profit, max_volume],
            COL_SELLER_ID: [max_profit, max_profit, max_volume],
            COL_PRICE_PAID: [100.0, 120.0, 40.0],
            COL_UNIT_COST: [20.0, 20.0, 10.0],
            COL_GROSS_MARGIN: [80.0, 100.0, 30.0],
        }
    ).select(list(TRANSACTIONS_COLUMNS))

    products = pl.DataFrame(
        {
            "listing_id": list(range(9)),
            "seller_id": list(range(9)),
            "unit_cost": [10.0] * 9,
            "price": [50.0] * 9,
            "demand_index": [1.0] * 9,
            "delivery_days": [3.0] * 9,
            "rating_value": [4.0] * 9,
        }
    )

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


def test_demand_matrix_strategy_by_pvd_segment_axes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = _build_run_with_transactions(Path(tmp))
        store = AnalyticsStore(run_root)
        try:
            raw = query_demand_matrix(store, tick_id=0)
        finally:
            store.close()

    assert raw["axis_x"] == "strategy_type"
    assert raw["axis_y"] == "pvd_segment"
    assert raw["x_labels"] == list(DEMAND_MATRIX_STRATEGY_ORDER)
    assert raw["y_labels"] == list(DEMAND_MATRIX_PVD_ORDER)
    assert len(raw["cells"]) == len(DEMAND_MATRIX_STRATEGY_ORDER) * len(DEMAND_MATRIX_PVD_ORDER)

    by_key = {(c["row"], c["col"]): c["density"] for c in raw["cells"]}
    rich_row = list(DEMAND_MATRIX_PVD_ORDER).index("rich")
    low_row = list(DEMAND_MATRIX_PVD_ORDER).index("low")
    profit_col = list(DEMAND_MATRIX_STRATEGY_ORDER).index("MaxProfit")
    volume_col = list(DEMAND_MATRIX_STRATEGY_ORDER).index("MaxVolume")

    assert by_key[(rich_row, profit_col)] > 0.0
    assert by_key[(low_row, volume_col)] > 0.0
    assert by_key[(rich_row, profit_col)] > by_key[(low_row, volume_col)]


def test_demand_matrix_empty_without_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = Path(tmp) / "bare"
        run_root.mkdir()
        (run_root / "transactions").mkdir()
        (run_root / "manifest.json").write_text('{"run_id":"bare"}', encoding="utf-8")
        store = AnalyticsStore(run_root)
        try:
            raw = query_demand_matrix(store, tick_id=0)
        finally:
            store.close()

    assert all(cell["density"] == 0.0 for cell in raw["cells"])
