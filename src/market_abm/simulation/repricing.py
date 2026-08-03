# Назначение файла: stress repricing profile и rule-tick (Slice 11.4, Spec 011 §5.3).
# Базовая идея: build_stress_repricing_profile + apply_repricing_tick с unit cost guard.
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from market_abm.config.inventory import InventoryPricingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.macro import MacroState
from market_abm.domain.constants import (
    COL_BASE_COMMISSION,
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_LOGISTIC_FEE,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STOCK_UNITS,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PLATFORM_DEFAULTS,
)
from market_abm.simulation.inventory import (
    COL_INVENTORY_PRESSURE,
    compute_inventory_pressure,
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
    panic_mode: bool = False
    repricing_speed_cap: int | None = None


_MIN_COMP_COL: str = "min_competitor_price"


def compute_competitor_prices(listings_df: pl.DataFrame) -> pl.DataFrame:
    """
    Vectorized per-category minimum competitor price (Spec 012 §4.3).

    Adds column `min_competitor_price` = min{P_k | category_k = category_j} for each listing j.

    Edge cases:
    - Listing is at category min price → min_comp = cat_min → Δ_comp = 0 → no undercut (correct).
    - Sole listing in category → min_comp = its own price → Δ_comp = 0 → no undercut (correct).

    One Polars group_by — O(n log n), called once per repricing tick.
    """
    cat_min = (
        listings_df
        .group_by(COL_CATEGORY_ID)
        .agg(pl.col(COL_PRICE).min().alias("_cat_min_price"))
    )
    return (
        listings_df
        .join(cat_min, on=COL_CATEGORY_ID, how="left")
        .with_columns(pl.col("_cat_min_price").cast(pl.Float32).alias(_MIN_COMP_COL))
        .drop("_cat_min_price")
    )


def build_stress_repricing_profile(
    macro: MacroState,
    config: RepricingConfig,
) -> RepricingProfile | None:
    """Строит stress profile или None если stress ниже порога."""
    stress_cfg = config.stress
    if macro.stress <= stress_cfg.stress_repricing_threshold:
        return None

    stress = float(macro.stress)
    panic_mode = stress >= stress_cfg.panic_stress_threshold
    step_gain = stress_cfg.panic_step_gain if panic_mode else stress_cfg.stress_step_gain
    volume_gain = (
        stress_cfg.panic_volume_gain if panic_mode else stress_cfg.stress_volume_gain
    )
    dead_zone_shrink = (
        stress_cfg.panic_dead_zone_shrink if panic_mode else stress_cfg.stress_dead_zone_shrink
    )

    return RepricingProfile(
        stress=stress,
        relative_step=config.relative_step * (1.0 + step_gain * stress),
        max_profit_demand_high=config.max_profit_demand_high
        - dead_zone_shrink * stress,
        max_profit_demand_low=config.max_profit_demand_low + dead_zone_shrink * stress,
        max_volume_aggression=config.max_volume_aggression * (1.0 + volume_gain * stress),
        panic_margin_above_unit_cost=stress_cfg.panic_margin_above_unit_cost,
        forbid_price_below_unit_cost=stress_cfg.forbid_price_below_unit_cost,
        panic_mode=panic_mode,
        repricing_speed_cap=(
            stress_cfg.panic_repricing_speed_cap if panic_mode else None
        ),
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


def _repricing_speed_expr(repricing_profile: RepricingProfile | None) -> pl.Expr:
    """Effective repricing speed: panic cap ускоряет реакцию без мутации sellers_df."""
    speed = pl.col(COL_REPRICING_SPEED)
    if repricing_profile is not None and repricing_profile.repricing_speed_cap is not None:
        speed = pl.min_horizontal(
            speed,
            pl.lit(repricing_profile.repricing_speed_cap, dtype=pl.UInt8),
        )
    return speed


def _panic_effective_demand_expr(repricing_profile: RepricingProfile | None) -> pl.Expr:
    """В panic-mode ограничиваем demand_index сверху stress-cap — иначе хвост не двигается."""
    demand = pl.col(COL_DEMAND_INDEX)
    if repricing_profile is not None and repricing_profile.panic_mode:
        stress_cap = pl.lit(
            max(0.0, 1.0 - repricing_profile.stress),
            dtype=pl.Float32,
        )
        return pl.min_horizontal(demand, stress_cap)
    return demand


def _active_repricing_mask(tick: int, repricing_profile: RepricingProfile | None) -> pl.Expr:
    speed = _repricing_speed_expr(repricing_profile)
    on_tick = pl.lit(tick, dtype=pl.UInt32) % speed == 0
    if repricing_profile is not None and repricing_profile.panic_mode:
        return on_tick
    return on_tick & (pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer"))


def _guarded_panic_drop_expr(
    step: pl.Expr,
    volume_aggression: float,
    repricing_profile: RepricingProfile,
) -> pl.Expr:
    drop_step = step * pl.lit(volume_aggression, dtype=pl.Float32)
    drop_candidate = pl.col(COL_PRICE) - drop_step
    panic_floor = pl.col(COL_UNIT_COST) + pl.lit(
        repricing_profile.panic_margin_above_unit_cost,
        dtype=pl.Float32,
    )
    return (
        pl.when(pl.col(COL_PRICE) > panic_floor)
        .then(pl.max_horizontal(drop_candidate, panic_floor))
        .otherwise(pl.col(COL_PRICE))
    )


def _max_volume_price_expr(
    step: pl.Expr,
    max_volume_aggression: float,
    repricing_profile: RepricingProfile | None,
    *,
    demand_index: pl.Expr,
) -> pl.Expr:
    drop_step = step * pl.lit(max_volume_aggression, dtype=pl.Float32)
    drop_candidate = pl.col(COL_PRICE) - drop_step
    rise_candidate = pl.col(COL_PRICE) + step * pl.lit(0.5, dtype=pl.Float32)

    if repricing_profile is not None and repricing_profile.panic_mode:
        return _guarded_panic_drop_expr(step, max_volume_aggression, repricing_profile)

    if repricing_profile is None or not repricing_profile.forbid_price_below_unit_cost:
        return (
            pl.when(demand_index < pl.lit(1.0, dtype=pl.Float32))
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
        pl.when(demand_index < pl.lit(1.0, dtype=pl.Float32))
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
    inventory_pricing: InventoryPricingConfig | None = None,
    sell_through_by_listing: dict[int, float] | None = None,
) -> pl.DataFrame:
    """Return new listings_df after one repricing tick.

    Preserves extra columns present in listings_df (e.g. category_id, stock_units)
    for downstream ranking / inventory across ticks (Spec 012 §7.1 / Spec 012.1).
    """
    if tick < 0:
        raise ValueError(f"tick must be >= 0, got {tick}")

    rel_step, demand_high, demand_low, volume_aggression = _resolve_effective_params(
        config,
        repricing_profile,
    )

    # Enrich with per-category competitor min price when enabled and category present
    has_competitor = (
        config.competitor.enabled
        and COL_CATEGORY_ID in listings_df.columns
    )
    work = compute_competitor_prices(listings_df) if has_competitor else listings_df

    joined = work.join(sellers_df, on=COL_SELLER_ID, how="left")

    step = pl.col(COL_PRICE) * pl.lit(rel_step, dtype=pl.Float32)
    p_min = min_price_from_margin(
        pl.col(COL_UNIT_COST),
        pl.col(COL_MARGIN_FLOOR),
        min_listing_price=config.min_listing_price,
    )
    active = _active_repricing_mask(tick, repricing_profile)
    effective_demand = _panic_effective_demand_expr(repricing_profile)

    max_profit_price = (
        pl.when(effective_demand > pl.lit(demand_high, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) + step)
        .when(effective_demand < pl.lit(demand_low, dtype=pl.Float32))
        .then(pl.col(COL_PRICE) - step)
        .otherwise(pl.col(COL_PRICE))
    )
    max_volume_price = _max_volume_price_expr(
        step,
        volume_aggression,
        repricing_profile,
        demand_index=effective_demand,
    )
    rating_panic_price = (
        _guarded_panic_drop_expr(step, volume_aggression, repricing_profile)
        if repricing_profile is not None and repricing_profile.panic_mode
        else pl.col(COL_PRICE)
    )

    strategy_price = (
        pl.when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxProfit"))
        .then(max_profit_price)
        .when(pl.col(COL_STRATEGY_TYPE) == pl.lit("MaxVolume"))
        .then(max_volume_price)
        .when(pl.col(COL_STRATEGY_TYPE) == pl.lit("RatingMaximizer"))
        .then(rating_panic_price)
        .otherwise(pl.col(COL_PRICE))
    )

    # Competitor undercut gate (Spec 012 §4.3):
    # when Δ_comp = (P_j - min_comp) / P_j > threshold → force one-step price drop
    # applied to MaxProfit / MaxVolume only (not RatingMaximizer).
    if has_competitor:
        comp_col = pl.col(_MIN_COMP_COL).cast(pl.Float32)
        price_safe = pl.col(COL_PRICE).clip(lower_bound=pl.lit(1e-6, dtype=pl.Float32))
        delta_comp = (pl.col(COL_PRICE) - comp_col) / price_safe
        undercut_trigger = (
            (delta_comp > pl.lit(config.competitor.undercut_threshold, dtype=pl.Float32))
            & (pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer"))
        )
        undercut_candidate = pl.col(COL_PRICE) - step
        # Competitor undercut overrides demand-signal when Δ_comp > threshold
        strategy_price = (
            pl.when(undercut_trigger)
            .then(pl.min_horizontal(strategy_price, undercut_candidate))
            .otherwise(strategy_price)
        )

    # Spec 012.1 §5.2: inventory pressure after competitor, before unit_cost / margin floors
    if (
        inventory_pricing is not None
        and inventory_pricing.enabled
        and COL_STOCK_UNITS in listings_df.columns
    ):
        pressure_df = compute_inventory_pressure(
            listings_df,
            inventory_pricing,
            sell_through_by_listing=sell_through_by_listing,
        )
        joined = joined.join(pressure_df, on=COL_LISTING_ID, how="left")
        inv_delta = (
            -pl.lit(float(inventory_pricing.inventory_step_gain), dtype=pl.Float32)
            * pl.col(COL_INVENTORY_PRESSURE).fill_null(0.0)
            * step
        )
        strategy_price = (
            pl.when(pl.col(COL_STRATEGY_TYPE) != pl.lit("RatingMaximizer"))
            .then(strategy_price + inv_delta)
            .otherwise(strategy_price)
        )

    clipped_price = pl.max_horizontal(strategy_price, p_min)
    if repricing_profile is not None and repricing_profile.forbid_price_below_unit_cost:
        clipped_price = pl.max_horizontal(clipped_price, pl.col(COL_UNIT_COST))
    final_price = pl.when(active).then(clipped_price).otherwise(pl.col(COL_PRICE))

    # Output: LISTINGS_COLUMNS + any extra columns from original listings_df
    # (drop ephemeral inventory_pressure if joined)
    extra_cols = [
        c
        for c in listings_df.columns
        if c not in set(LISTINGS_COLUMNS) and c != COL_INVENTORY_PRESSURE
    ]
    out_cols = list(LISTINGS_COLUMNS) + extra_cols
    return joined.with_columns(final_price.alias(COL_PRICE)).select(out_cols)


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
    active = _active_repricing_mask(tick, repricing_profile)
    candidate = pl.max_horizontal(pl.col(next_col), p_min)
    if repricing_profile is not None and repricing_profile.forbid_price_below_unit_cost:
        candidate = pl.max_horizontal(candidate, pl.col(COL_UNIT_COST))
    final_price = pl.when(active).then(candidate).otherwise(pl.col(COL_PRICE))

    extra_cols_ml = [c for c in listings_df.columns if c not in set(LISTINGS_COLUMNS)]
    out_cols_ml = list(LISTINGS_COLUMNS) + extra_cols_ml
    return joined.with_columns(final_price.alias(COL_PRICE)).select(out_cols_ml)
