# Назначение файла: чистые трансформеры шоков среды (Slice 8.1).
# Базовая идея: apply_environment_shocks возвращает новые DataFrame, не in-place.
from __future__ import annotations

import polars as pl

from market_abm.config.shocks import ShockCatalogConfig, ShockEffectSpec
from market_abm.domain.constants import (
    COL_BUDGET,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_UNIT_COST,
)
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.simulation.context import SimulationContext

COL_PROMOTION_ANCHOR: str = "promotion_anchor_price"


def _active_shock(ctx: SimulationContext, shock_type: ShockType) -> ActiveShock | None:
    for shock in ctx.active_shocks:
        if shock.shock_type == shock_type:
            return shock
    return None


def _promotion_discount(ctx: SimulationContext, catalog: ShockCatalogConfig) -> float:
    shock = _active_shock(ctx, ShockType.MARKETPLACE_PROMOTION)
    if shock is None:
        return 0.0
    return catalog.marketplace_promotion.fee_delta * shock.intensity


def drop_promotion_columns(products_df: pl.DataFrame) -> pl.DataFrame:
    """Убирает runtime-колонку якоря акции перед persist."""
    if COL_PROMOTION_ANCHOR in products_df.columns:
        return products_df.drop(COL_PROMOTION_ANCHOR)
    return products_df


def apply_marketplace_promotion_caps(
    products_df: pl.DataFrame,
    ctx: SimulationContext | None,
    catalog: ShockCatalogConfig,
) -> pl.DataFrame:
    """
    Жёсткий потолок цены во время акции маркетплейса:
    final_allowed_price = anchor_price * (1 - discount).
    Repricers не могут поднять цену выше потолка на последующих тиках.
    """
    if ctx is None or _active_shock(ctx, ShockType.MARKETPLACE_PROMOTION) is None:
        return drop_promotion_columns(products_df)

    discount = _promotion_discount(ctx, catalog)
    if discount <= 0.0 or products_df.height == 0:
        return products_df

    df = products_df
    if COL_PROMOTION_ANCHOR not in df.columns:
        df = df.with_columns(pl.col(COL_PRICE).alias(COL_PROMOTION_ANCHOR))

    cap = (pl.col(COL_PROMOTION_ANCHOR) * (1.0 - pl.lit(discount, dtype=pl.Float32))).cast(
        pl.Float32
    )
    return df.with_columns(
        pl.max_horizontal(
            pl.min_horizontal(pl.col(COL_PRICE), cap),
            pl.col(COL_UNIT_COST),
        )
        .cast(pl.Float32)
        .alias(COL_PRICE)
    )


def apply_environment_shocks(
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    ctx: SimulationContext | None,
    catalog: ShockCatalogConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Применяет активные шоки из ctx к buyers_df и products_df.
    Без ctx — identity (клоны входных таблиц).
    """
    if ctx is None or not ctx.active_shocks:
        return buyers_df.clone(), drop_promotion_columns(products_df.clone())

    buyers_out = buyers_df.clone()
    products_out = products_df.clone()

    ordered = sorted(ctx.active_shocks, key=lambda s: s.shock_type.value)

    for shock in ordered:
        buyers_out, products_out = _apply_single_shock(
            buyers_out,
            products_out,
            shock,
            ctx.platform_fee_rate,
            catalog,
        )

    products_out = apply_marketplace_promotion_caps(products_out, ctx, catalog)
    return buyers_out, products_out


def _apply_demand_shock_to_buyers(
    buyers_df: pl.DataFrame,
    spec: ShockEffectSpec,
    intensity: float,
) -> pl.DataFrame:
    """Масштабирует budget и (опционально) purchase_frequency; baseline не трогает."""
    if buyers_df.height == 0:
        return buyers_df

    budget_mult = spec.budget_multiplier * intensity
    buyers_df = buyers_df.with_columns(
        (pl.col(COL_BUDGET) * budget_mult).cast(pl.Float32).alias(COL_BUDGET)
    )

    if spec.scale_purchase_frequency:
        freq_mult = spec.purchase_frequency_multiplier * intensity
        buyers_df = buyers_df.with_columns(
            (pl.col(COL_PURCHASE_FREQUENCY) * freq_mult)
            .clip(0.0, 1.0)
            .cast(pl.Float32)
            .alias(COL_PURCHASE_FREQUENCY)
        )

    return buyers_df


def _apply_single_shock(
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    shock: ActiveShock,
    platform_fee_rate: float,
    catalog: ShockCatalogConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    intensity = shock.intensity

    if shock.shock_type == ShockType.DEMAND_CRASH:
        buyers_df = _apply_demand_shock_to_buyers(
            buyers_df, catalog.demand_crash, intensity
        )

    elif shock.shock_type == ShockType.DEMAND_BOOM:
        buyers_df = _apply_demand_shock_to_buyers(
            buyers_df, catalog.demand_boom, intensity
        )

    elif shock.shock_type == ShockType.PLATFORM_FEE_HIKE:
        if products_df.height > 0:
            mult = 1.0 + platform_fee_rate + catalog.platform_fee_hike.fee_delta * intensity
            products_df = products_df.with_columns(
                (pl.col(COL_PRICE) * mult).cast(pl.Float32).alias(COL_PRICE)
            )

    elif shock.shock_type == ShockType.PLATFORM_FEE_CUT:
        if products_df.height > 0:
            mult = 1.0 + platform_fee_rate - catalog.platform_fee_cut.fee_delta * intensity
            products_df = products_df.with_columns(
                pl.max_horizontal(
                    pl.col(COL_PRICE) * mult,
                    pl.col(COL_UNIT_COST),
                )
                .cast(pl.Float32)
                .alias(COL_PRICE)
            )

    elif shock.shock_type == ShockType.MARKETPLACE_PROMOTION:
        # Ценовой потолок применяется в apply_marketplace_promotion_caps после всех шоков.
        pass

    elif shock.shock_type == ShockType.SUPPLY_SHOCK:
        if products_df.height > 0:
            mult = catalog.supply_shock.supply_cost_multiplier * intensity
            products_df = products_df.with_columns(
                (pl.col(COL_UNIT_COST) * mult).cast(pl.Float32).alias(COL_UNIT_COST)
            )

    return buyers_df, products_df
