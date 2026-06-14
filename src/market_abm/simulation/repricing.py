# Назначение файла: stress repricing profile и rule-tick (Slice 11.4, Spec 011 §5.3).
# Базовая идея: build_stress_repricing_profile + apply_repricing_tick с unit cost guard.
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from market_abm.config.repricing import RepricingConfig
from market_abm.domain.macro import MacroState
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


@dataclass(frozen=True)
class RepricingProfile:
    """Effective repricing thresholds при macro.stress > threshold."""

    stress: float
    relative_step: float
    max_profit_demand_high: float
    max_profit_demand_low: float
    max_volume_aggression: float
    panic_margin_above_unit_cost: float
    forbid_price_below_unit_cost: bool


def build_stress_repricing_profile(
    macro: MacroState,
    config: RepricingConfig,
) -> RepricingProfile | None:
    """Строит stress profile или None если stress ниже порога."""
    stress_cfg = config.stress
    if macro.stress <= stress_cfg.stress_repricing_threshold:
        return None

    stress = float(macro.stress)
    return RepricingProfile(
        stress=stress,
        relative_step=config.relative_step * (1.0 + stress_cfg.stress_step_gain * stress),
        max_profit_demand_high=config.max_profit_demand_high
        - stress_cfg.stress_dead_zone_shrink * stress,
        max_profit_demand_low=config.max_profit_demand_low
        + stress_cfg.stress_dead_zone_shrink * stress,
        max_volume_aggression=config.max_volume_aggression
        * (1.0 + stress_cfg.stress_volume_gain * stress),
        panic_margin_above_unit_cost=stress_cfg.panic_margin_above_unit_cost,
        forbid_price_below_unit_cost=stress_cfg.forbid_price_below_unit_cost,
    )


def min_price_from_margin(
    unit_cost: pl.Expr,
    margin_floor: pl.Expr,
    *,
    min_listing_price: float = 0.0,
) -> pl.Expr:
    """p_min = max(cost / (1 - margin - fees), absolute min_listing_price)."""
    total_fees = (
        PLATFORM_DEFAULTS[COL_BASE_COMMISSION] + PLATFORM_DEFAULTS[COL_LOGISTIC_FEE]
    )
    margin_based = unit_cost / (1.0 - margin_floor - pl.lit(total_fees, dtype=pl.Float32))
    if min_listing_price > 0.0:
        return pl.max_horizontal(
            margin_based,
            pl.lit(min_listing_price, dtype=pl.Float32),
        )
    return margin_based


def _resolve_effective_params(
    config: RepricingConfig,
    repricing_profile: RepricingProfile | None,
) -> tuple[float, float, float, float]:
    if repricing_profile is None:
        return (
            config.relative_step,
            config.max_profit_demand_high,
            config.max_profit_demand_low,
            config.max_volume_aggression,
        )
    return (
        repricing_profile.relative_step,
        repricing_profile.max_profit_demand_high,
        repricing_profile.max_profit_demand_low,
        repricing_profile.max_volume_aggression,
    )


def _max_volume_price_expr(
    step: pl.Expr,
    max_volume_aggression: float,
    repricing_profile: RepricingProfile | None,
) -> pl.Expr:
    drop_step = step * pl.lit(max_volume_aggression, dtype=pl.Float32)
    drop_candidate = pl.col(COL_PRICE) - drop_step
    rise_candidate = pl.col(COL_PRICE) + step * pl.lit(0.5, dtype=pl.Float32)

    if repricing_profile is None or not repricing_profile.forbid_price_below_unit_cost:
        return (
            pl.when(pl.col(COL_DEMAND_INDEX) < pl.lit(1.0, dtype=pl.Float32))
            .then(drop_candidate)
            .otherwise(rise_candidate)
        )

    panic_floor = pl.col(COL_UNIT_COST) + pl.lit(
        repricing_profile.panic_margin_above_unit_cost,
        dtype=pl.Float32,
    )
    guarded_drop = (
        pl.when(pl.col(COL_PRICE) > panic_floor)
        .then(pl.max_horizontal(drop_candidate, panic_floor))
        .otherwise(pl.col(COL_PRICE))
    )
    return (
        pl.when(pl.col(COL_DEMAND_INDEX) < pl.lit(1.0, dtype=pl.Float32))
        .then(guarded_drop)
        .otherwise(rise_candidate)
    )


def apply_repricing_tick(
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    *,
    tick: int,
    config: RepricingConfig,
    repricing_profile: RepricingProfile | None = None,
) -> pl.DataFrame:
    """Return new listings_df after one repricing tick."""
    if tick < 0:
        raise ValueError(f"tick must be >= 0, got {tick}")

    rel_step, demand_high, demand_low, volume_aggression = _resolve_effective_params(
        config,
        repricing_profile,
    )

    joined = listings_df.join(sellers_df, on=COL_SELLER_ID, how="left")

    step = pl.col(COL_PRICE) * pl.lit(rel_step, dtype=pl.Float32)
    p_min = min_price_from_margin(
        pl.col(COL_UNIT_COST),
        pl.col(COL_MARGIN_FLOOR),
        min_listing_price=config.min_listing_price,
    )
    active = (
        (pl.lit(tick, dtype=pl.UInt32) % pl.col(COL_REPRICING_SPEED) == 0)
        & (pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer"))
    )

    max_profit_price = (
        pl.when(pl.col(COL_DEMAND_INDEX) > pl.lit(demand_high, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) + step)
        .when(pl.col(COL_DEMAND_INDEX) < pl.lit(demand_low, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) - step)
        .otherwise(pl.col(COL_PRICE))
    )
    max_volume_price = _max_volume_price_expr(step, volume_aggression, repricing_profile)

    strategy_price = (
        pl.when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxProfit"))
        .then(max_profit_price)
        .when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxVolume"))
        .then(max_volume_price)
        .otherwise(pl.col(COL_PRICE))
    )
    clipped_price = pl.max_horizontal(strategy_price, p_min)
    if repricing_profile is not None and repricing_profile.forbid_price_below_unit_cost:
        clipped_price = pl.max_horizontal(clipped_price, pl.col(COL_UNIT_COST))
    final_price = pl.when(active).then(clipped_price).otherwise(pl.col(COL_PRICE))

    return joined.with_columns(final_price.alias(COL_PRICE)).select(list(LISTINGS_COLUMNS))


def apply_ml_repricing_tick(
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    *,
    next_prices: np.ndarray,
    tick: int,
    config: RepricingConfig,
    repricing_profile: RepricingProfile | None = None,
) -> pl.DataFrame:
    """
    Векторное применение ML next_prices (Spec 005 §4.4) — функциональное зеркало apply_repricing_tick.

    next_prices выровнены по порядку строк listings_df. Маска активности и no-op RatingMaximizer
    идентичны rule-пути (002); нижний клип — min_price_from_margin. Без row-wise цикла (V2).
    """
    if tick < 0:
        raise ValueError(f"tick must be >= 0, got {tick}")

    next_col = "_ml_next_price"
    listings_with = listings_df.with_columns(
        pl.Series(next_col, np.asarray(next_prices, dtype=np.float32))
    )
    joined = listings_with.join(sellers_df, on=COL_SELLER_ID, how="left")

    p_min = min_price_from_margin(
        pl.col(COL_UNIT_COST),
        pl.col(COL_MARGIN_FLOOR),
        min_listing_price=config.min_listing_price,
    )
    active = (pl.lit(tick, dtype=pl.UInt32) % pl.col(COL_REPRICING_SPEED) == 0) & (
        pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer")
    )
    candidate = pl.max_horizontal(pl.col(next_col), p_min)
    if repricing_profile is not None and repricing_profile.forbid_price_below_unit_cost:
        candidate = pl.max_horizontal(candidate, pl.col(COL_UNIT_COST))
    final_price = pl.when(active).then(candidate).otherwise(pl.col(COL_PRICE))

    return joined.with_columns(final_price.alias(COL_PRICE)).select(list(LISTINGS_COLUMNS))
