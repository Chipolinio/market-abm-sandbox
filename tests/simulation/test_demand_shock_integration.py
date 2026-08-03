# Spec 010 §10.4 — integration A+B: demand crash снижает GMV при ценах у p_min.
from __future__ import annotations

import polars as pl

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.shocks import ShockCatalogConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    PLATFORM_DEFAULTS,
)
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.population.buyers import generate_buyers
from market_abm.simulation.context import SimulationContext
from market_abm.simulation.repricing import min_price_from_margin
from market_abm.simulation.shocks import apply_environment_shocks
from market_abm.simulation.step import _select_active_buyers, _step_rng, step


def _floor_price(unit_cost: float, margin_floor: float) -> float:
    joined = pl.DataFrame(
        {
            COL_UNIT_COST: [unit_cost],
            COL_MARGIN_FLOOR: [margin_floor],
        }
    )
    return float(
        joined.select(
            min_price_from_margin(pl.col(COL_UNIT_COST), pl.col(COL_MARGIN_FLOOR)).alias("p_min")
        )["p_min"][0]
    )


def _integration_step_config(tick_id: int, seed: int) -> SimulationStepConfig:
    return SimulationStepConfig(
        tick_id=tick_id,
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            outside_utility_bias=-100.0,
            income_utility_gamma=0.35,
            max_products_per_choice_set=50,
            buyers_batch_size=500,
        ),
        repricing=RepricingConfig.default_market(),
    )


def _crash_context(tick_id: int) -> SimulationContext:
    return SimulationContext(
        tick_id=tick_id,
        active_shocks=(
            ActiveShock(
                shock_type=ShockType.DEMAND_CRASH,
                intensity=1.0,
                remaining_ticks=10,
                applied_at_tick=tick_id,
            ),
        ),
        platform_fee_rate=PLATFORM_DEFAULTS["base_commission"],
    )


def _floor_market() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    buyers = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=300, seed=10))
    buyers = buyers.with_columns(pl.lit(1.0, dtype=pl.Float32).alias(COL_PURCHASE_FREQUENCY))

    unit_cost = 20.0
    margin_floor = 0.2
    floor = _floor_price(unit_cost, margin_floor)
    seller_ids = [0, 1, 2]

    sellers = pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: ["RatingMaximizer", "RatingMaximizer", "RatingMaximizer"],
            "capital": [1000.0] * 3,
            COL_MARGIN_FLOOR: [margin_floor] * 3,
            COL_REPRICING_SPEED: [1, 1, 1],
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )

    products = pl.DataFrame(
        {
            COL_LISTING_ID: seller_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [unit_cost] * 3,
            COL_PRICE: [floor] * 3,
            COL_DEMAND_INDEX: [1.0] * 3,
            COL_DELIVERY_DAYS: [3.0] * 3,
            COL_RATING_VALUE: [4.0] * 3,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )
    return buyers, sellers, products


def _step_metrics(
    buyers: pl.DataFrame,
    sellers: pl.DataFrame,
    products: pl.DataFrame,
    *,
    tick_id: int,
    seed: int,
    simulation_context: SimulationContext | None,
) -> tuple[int, float, int, float, pl.DataFrame]:
    cfg = _integration_step_config(tick_id, seed)
    rng = _step_rng(cfg)
    catalog = ShockCatalogConfig()
    buyers_work, _ = apply_environment_shocks(
        buyers, products.clone(), simulation_context, catalog
    )
    active = _select_active_buyers(buyers_work, rng).height
    products_next, tx, _, _ = step(
        buyers,
        sellers,
        products,
        cfg,
        simulation_context=simulation_context,
    )
    gmv = float(tx[COL_PRICE_PAID].sum()) if tx.height > 0 else 0.0
    conversion = tx.height / active if active > 0 else 0.0
    return active, gmv, tx.height, conversion, products_next


def test_crash_lowers_gmv_when_prices_at_floor() -> None:
    buyers, sellers, products = _floor_market()
    _, gmv0, txn0, _, products1 = _step_metrics(
        buyers, sellers, products, tick_id=0, seed=99, simulation_context=None
    )
    assert gmv0 > 0.0
    assert txn0 > 0

    _, gmv1, _, _, _ = _step_metrics(
        buyers,
        sellers,
        products1,
        tick_id=1,
        seed=99,
        simulation_context=_crash_context(1),
    )
    assert gmv1 < gmv0


def test_crash_lowers_active_buyers_and_conversion() -> None:
    buyers, sellers, products = _floor_market()
    active0, _, txn0, conv0, products1 = _step_metrics(
        buyers, sellers, products, tick_id=0, seed=88, simulation_context=None
    )
    active1, _, txn1, conv1, _ = _step_metrics(
        buyers,
        sellers,
        products1,
        tick_id=1,
        seed=88,
        simulation_context=_crash_context(1),
    )

    assert active1 < active0
    assert txn1 <= txn0
    assert conv1 < conv0


def test_deterministic_with_fixed_seed() -> None:
    buyers, sellers, products = _floor_market()
    _, gmv_a, txn_a, _, products1 = _step_metrics(
        buyers, sellers, products, tick_id=5, seed=77, simulation_context=None
    )
    assert gmv_a > 0.0

    _, gmv_b, txn_b, _, _ = _step_metrics(
        buyers,
        sellers,
        products1,
        tick_id=6,
        seed=77,
        simulation_context=_crash_context(6),
    )
    _, gmv_c, txn_c, _, _ = _step_metrics(
        buyers,
        sellers,
        products1,
        tick_id=6,
        seed=77,
        simulation_context=_crash_context(6),
    )

    assert gmv_b == gmv_c
    assert txn_b == txn_c
