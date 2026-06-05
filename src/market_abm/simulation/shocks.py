# Назначение файла: чистые трансформеры шоков среды (Slice 8.1).
# Базовая идея: apply_environment_shocks возвращает новые DataFrame, не in-place.
from __future__ import annotations

import polars as pl

from market_abm.config.shocks import ShockCatalogConfig
from market_abm.domain.constants import COL_BUDGET, COL_PRICE, COL_UNIT_COST
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.simulation.context import SimulationContext


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
        return buyers_df.clone(), products_df.clone()

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

    return buyers_out, products_out


def _apply_single_shock(
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    shock: ActiveShock,
    platform_fee_rate: float,
    catalog: ShockCatalogConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    intensity = shock.intensity

    if shock.shock_type == ShockType.DEMAND_CRASH:
        if buyers_df.height > 0:
            mult = catalog.demand_crash.budget_multiplier * intensity
            buyers_df = buyers_df.with_columns(
                (pl.col(COL_BUDGET) * mult).cast(pl.Float32).alias(COL_BUDGET)
            )

    elif shock.shock_type == ShockType.DEMAND_BOOM:
        if buyers_df.height > 0:
            mult = catalog.demand_boom.budget_multiplier * intensity
            buyers_df = buyers_df.with_columns(
                (pl.col(COL_BUDGET) * mult).cast(pl.Float32).alias(COL_BUDGET)
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

    elif shock.shock_type == ShockType.SUPPLY_SHOCK:
        if products_df.height > 0:
            mult = catalog.supply_shock.supply_cost_multiplier * intensity
            products_df = products_df.with_columns(
                (pl.col(COL_UNIT_COST) * mult).cast(pl.Float32).alias(COL_UNIT_COST)
            )

    return buyers_df, products_df
