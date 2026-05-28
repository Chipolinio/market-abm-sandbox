# Purpose: Apply one vectorized repricing tick to listings_df.
# Core idea: Use strategy-based pure transformations with hard price floor clipping.
from __future__ import annotations

import polars as pl

from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import (
    COL_BASE_COMMISSION,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_LOGISTIC_FEE,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PLATFORM_DEFAULTS,
)


def min_price_from_margin(unit_cost: pl.Expr, margin_floor: pl.Expr) -> pl.Expr:
    """Build expression for p_min = cost / (1 - margin_floor - base_commission - logistic_fee)."""
    total_fees = (
        PLATFORM_DEFAULTS[COL_BASE_COMMISSION] + PLATFORM_DEFAULTS[COL_LOGISTIC_FEE]
    )
    return unit_cost / (1.0 - margin_floor - pl.lit(total_fees, dtype=pl.Float32))


def apply_repricing_tick(
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    *,
    tick: int,
    config: RepricingConfig,
) -> pl.DataFrame:
    """Return new listings_df after one repricing tick."""
    if tick < 0:
        raise ValueError(f"tick must be >= 0, got {tick}")

    joined = listings_df.join(sellers_df, on=COL_SELLER_ID, how="left")

    step = pl.col(COL_PRICE) * pl.lit(config.relative_step, dtype=pl.Float32)
    p_min = min_price_from_margin(pl.col(COL_UNIT_COST), pl.col(COL_MARGIN_FLOOR))
    active = (
        (pl.lit(tick, dtype=pl.UInt32) % pl.col(COL_REPRICING_SPEED) == 0)
        & (pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer"))
    )

    max_profit_price = (
        pl.when(pl.col(COL_DEMAND_INDEX) > pl.lit(config.max_profit_demand_high, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) + step)
        .when(pl.col(COL_DEMAND_INDEX) < pl.lit(config.max_profit_demand_low, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) - step)
        .otherwise(pl.col(COL_PRICE))
    )
    max_volume_price = (
        pl.when(pl.col(COL_DEMAND_INDEX) < pl.lit(1.0, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) - step * pl.lit(config.max_volume_aggression, dtype=pl.Float32))
        .otherwise(pl.col(COL_PRICE) + step * pl.lit(0.5, dtype=pl.Float32))
    )

    strategy_price = (
        pl.when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxProfit"))
        .then(max_profit_price)
        .when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxVolume"))
        .then(max_volume_price)
        .otherwise(pl.col(COL_PRICE))
    )
    clipped_price = pl.max_horizontal(strategy_price, p_min)
    final_price = pl.when(active).then(clipped_price).otherwise(pl.col(COL_PRICE))

    return joined.with_columns(final_price.alias(COL_PRICE)).select(list(LISTINGS_COLUMNS))
