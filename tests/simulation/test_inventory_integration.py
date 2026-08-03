# Spec 012.1, Slice 12.1.4: leaders DTO + seed stability + Spec 011 unit_cost regress.

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from market_abm.analytics.leaders import query_market_leaders, write_sellers_state_snapshot
from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
    write_reference_snapshots,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.inventory import InventoryConfig, InventoryPricingConfig
from market_abm.config.ranking import RankingConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_CATEGORY_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    PLATFORM_DEFAULTS,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.population.buyers import generate_buyers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.repricing import apply_repricing_tick, build_stress_repricing_profile
from market_abm.simulation.step import step

_SEED = 42


def _sellers_df(n: int, *, capital: float = 5_000.0) -> pl.DataFrame:
    return (
        pl.DataFrame(
            {
                COL_SELLER_ID: list(range(n)),
                COL_STRATEGY_TYPE: ["MaxProfit"] * n,
                "capital": [capital] * n,
                COL_MARGIN_FLOOR: [0.05] * n,
                COL_REPRICING_SPEED: [1] * n,
            }
        )
        .with_columns(
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
            pl.col("capital").cast(pl.Float32),
            pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
            pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
        )
        .select(list(SELLERS_COLUMNS))
    )


def _sellers_state(n: int, *, capital: float = 5_000.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_WORKING_CAPITAL: [capital] * n,
            COL_IS_BANKRUPT: [False] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )


def _products_with_stock(
    *,
    stocks: list[int],
    prices: list[float] | None = None,
    unit_costs: list[float] | None = None,
) -> pl.DataFrame:
    n = len(stocks)
    prices = prices or [80.0] * n
    unit_costs = unit_costs or [20.0] * n
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: unit_costs,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
            COL_CATEGORY_ID: [0] * n,
            COL_STOCK_UNITS: stocks,
            COL_STOCK_TARGET: stocks,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col(COL_STOCK_UNITS).cast(pl.Int32),
        pl.col(COL_STOCK_TARGET).cast(pl.Int32),
    )


def _buyers_df(n: int, *, freq: float = 0.8, budget: float = 500.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [budget] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [freq] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
    )


def _step_cfg(**kwargs: object) -> SimulationStepConfig:
    defaults: dict[str, object] = {
        "tick_id": 0,
        "seed": _SEED,
        "choice": ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=20,
            outside_utility_bias=-50.0,
            ranking=RankingConfig(top_k=5, organic_m=0, n_categories=2),
        ),
        "repricing": RepricingConfig.default_market(),
        "inventory": InventoryConfig(enabled=True),
        "inventory_pricing": InventoryPricingConfig(enabled=True),
    }
    defaults.update(kwargs)
    return SimulationStepConfig(**defaults)


def _empty_tx() -> pl.DataFrame:
    return pl.DataFrame(
        {col: [] for col in TRANSACTIONS_COLUMNS},
        schema={
            "tick_id": pl.Int32,
            COL_BUYER_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_PRICE_PAID: pl.Float32,
            COL_UNIT_COST: pl.Float32,
            "gross_margin": pl.Float32,
        },
    )


# ---------------------------------------------------------------------------
# 12.1.4-T1  leaders_inventory_stock_is_units
# ---------------------------------------------------------------------------


def test_12_1_4_t1_leaders_inventory_stock_is_units(tmp_path: Path) -> None:
    """DTO inventory_stock == sum(stock_units), not count(listings)."""
    stocks = [47, 3]  # deliberately ≠ 1 listing each
    sellers = _sellers_df(2)
    state = _sellers_state(2)
    products = _products_with_stock(stocks=stocks)
    assert products.height == 2  # one listing per seller
    assert stocks != [1, 1]

    config = SimulationRunConfig(
        seed=_SEED,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id="inv-leaders"
        ),
    )
    buyers_df = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=10, seed=_SEED))
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=_SEED,
        min_listing_price=config.repricing.min_listing_price,
    )
    ctx = init_run_directory(
        config,
        run_id="inv-leaders",
        buyers_df=buyers_df,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=1,
    )
    write_reference_snapshots(ctx.run_root, buyers_df=buyers_df, sellers_df=sellers)
    write_sellers_state_snapshot(ctx.run_root, tick_id=0, sellers_state_df=state)
    con = open_duckdb_connection(config.persistence)
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=_empty_tx(),
            products_df=products,
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()

    store = AnalyticsStore(ctx.run_root)
    try:
        raw = query_market_leaders(store, tick_id=0, limit=5, rank_by="working_capital")
    finally:
        store.close()

    by_seller = {int(row["seller_id"]): int(row["inventory_stock"]) for row in raw["leaders"]}
    assert by_seller[0] == 47
    assert by_seller[1] == 3
    assert by_seller[0] != 1  # not listing-count stub


# ---------------------------------------------------------------------------
# 12.1.4-T2  seed_stable_stock_path
# ---------------------------------------------------------------------------


def test_12_1_4_t2_seed_stable_stock_path() -> None:
    """Same seed → identical stock_units series and GMV across ticks."""
    n_ticks = 5

    def _run(seed: int) -> tuple[list[list[int]], list[float]]:
        buyers = _buyers_df(30, freq=0.9)
        products = _products_with_stock(stocks=[40, 40, 40], prices=[60.0, 70.0, 80.0])
        sellers = _sellers_df(products.height)
        state = _sellers_state(products.height)
        stock_series: list[list[int]] = []
        gmvs: list[float] = []
        for tick_id in range(n_ticks):
            cfg = _step_cfg(tick_id=tick_id, seed=seed)
            products, tx, state, _ = step(
                buyers, sellers, products, cfg, sellers_state_df=state
            )
            stock_series.append(products.sort(COL_LISTING_ID)[COL_STOCK_UNITS].to_list())
            gmvs.append(float(tx[COL_PRICE_PAID].sum()) if tx.height > 0 else 0.0)
        return stock_series, gmvs

    stocks_a, gmv_a = _run(_SEED)
    stocks_b, gmv_b = _run(_SEED)
    assert stocks_a == stocks_b
    assert gmv_a == gmv_b
    assert any(g > 0.0 for g in gmv_a), "fixture must produce non-zero GMV"
    # Stock must move (sales or at least not all frozen at init)
    assert stocks_a[0] != stocks_a[-1] or any(g > 0 for g in gmv_a)


# ---------------------------------------------------------------------------
# 12.1.4-T3  spec011_unit_cost_still_holds
# ---------------------------------------------------------------------------


def test_12_1_4_t3_spec011_unit_cost_still_holds() -> None:
    """Inventory pressure + panic stress never push price below unit_cost."""
    n = 6
    unit_costs = [50.0 + 10.0 * i for i in range(n)]
    prices = [u * 1.05 for u in unit_costs]
    listings = pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: unit_costs,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [0.2] * n,  # soft demand → MaxProfit dumps
            COL_CATEGORY_ID: [0] * n,
            COL_STOCK_UNITS: [500] * n,  # excess → inventory dump pressure
            COL_STOCK_TARGET: [20] * n,
            **{k: [v] * n for k, v in PLATFORM_DEFAULTS.items()},
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col(COL_STOCK_UNITS).cast(pl.Int32),
        pl.col(COL_STOCK_TARGET).cast(pl.Int32),
        *[pl.col(k).cast(pl.Float32) for k in PLATFORM_DEFAULTS],
    )
    sellers = (
        pl.DataFrame(
            {
                COL_SELLER_ID: list(range(n)),
                COL_STRATEGY_TYPE: ["MaxVolume"] * n,
                "capital": [500.0] * n,
                COL_MARGIN_FLOOR: [0.0] * n,
                COL_REPRICING_SPEED: [1] * n,
            }
        )
        .with_columns(
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
            pl.col("capital").cast(pl.Float32),
            pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
            pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
        )
    )
    cfg = RepricingConfig.market_with_headroom()
    macro = MacroState(
        stress=0.95,
        regime=MacroRegime.STRESS,
        peak_stress=0.95,
    )
    profile = build_stress_repricing_profile(macro, cfg)
    assert profile is not None and profile.panic_mode

    out = apply_repricing_tick(
        sellers,
        listings,
        tick=10,
        config=cfg,
        repricing_profile=profile,
        inventory_pricing=InventoryPricingConfig(
            enabled=True, inventory_step_gain=50.0, pressure_alpha=1.0
        ),
    )
    for i in range(n):
        assert float(out[COL_PRICE][i]) >= float(out[COL_UNIT_COST][i]) - 1e-4
