# Назначение файла: runtime-экономика селлеров — sellers_state_df (Slice 8.2).
# Базовая идея: init / settle / filter — чистые векторные трансформеры Polars.
from __future__ import annotations

import polars as pl

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.domain.constants import (
    COL_CAPITAL,
    COL_IS_BANKRUPT,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    SELLERS_STATE_COLUMNS,
    SELLERS_STATE_SCHEMA_DTYPES,
)


def _sellers_state_schema() -> dict[str, pl.DataType]:
    return {name: getattr(pl, dtype) for name, dtype in SELLERS_STATE_SCHEMA_DTYPES.items()}


def init_sellers_state(sellers_df: pl.DataFrame) -> pl.DataFrame:
    """working_capital = sellers_df.capital; is_bankrupt = False."""
    return pl.DataFrame(
        {
            COL_SELLER_ID: sellers_df[COL_SELLER_ID],
            COL_WORKING_CAPITAL: sellers_df[COL_CAPITAL],
            COL_IS_BANKRUPT: [False] * sellers_df.height,
        },
        schema=_sellers_state_schema(),
    )


def _aggregate_tick_economics(transactions_df: pl.DataFrame) -> pl.DataFrame:
    if transactions_df.height == 0:
        return pl.DataFrame(
            {
                COL_SELLER_ID: pl.Series([], dtype=pl.Int32),
                "revenue": pl.Series([], dtype=pl.Float32),
                "cogs": pl.Series([], dtype=pl.Float32),
            }
        )
    return transactions_df.group_by(COL_SELLER_ID).agg(
        pl.col(COL_PRICE_PAID).sum().cast(pl.Float32).alias("revenue"),
        pl.col(COL_UNIT_COST).sum().cast(pl.Float32).alias("cogs"),
    )


def settle_seller_economics(
    sellers_state_df: pl.DataFrame,
    transactions_df: pl.DataFrame,
    config: SellerEconomicsConfig,
) -> pl.DataFrame:
    """
    1) fixed_cost_per_tick — по всем не-bankrupt
    2) revenue = SUM(price_paid) по seller_id
    3) cogs = SUM(unit_cost) по seller_id (qty=1 на транзакцию)
    4) working_capital += revenue - cogs - fixed_cost
    5) is_bankrupt необратимо; True если capital <= threshold
    """
    agg = _aggregate_tick_economics(transactions_df)
    joined = sellers_state_df.join(agg, on=COL_SELLER_ID, how="left").with_columns(
        pl.col("revenue").fill_null(0.0).cast(pl.Float32),
        pl.col("cogs").fill_null(0.0).cast(pl.Float32),
    )

    fixed_cost = (
        pl.when(pl.col(COL_IS_BANKRUPT))
        .then(pl.lit(0.0, dtype=pl.Float32))
        .otherwise(pl.lit(config.fixed_cost_per_tick, dtype=pl.Float32))
    )

    new_capital = (
        pl.col(COL_WORKING_CAPITAL)
        + pl.col("revenue")
        - pl.col("cogs")
        - fixed_cost
    ).cast(pl.Float32)

    threshold = pl.lit(config.bankruptcy_threshold, dtype=pl.Float32)
    new_bankrupt = pl.col(COL_IS_BANKRUPT) | (new_capital <= threshold)

    return joined.with_columns(
        new_capital.alias(COL_WORKING_CAPITAL),
        new_bankrupt.alias(COL_IS_BANKRUPT),
    ).select(list(SELLERS_STATE_COLUMNS))


def filter_bankrupt_listings(
    products_df: pl.DataFrame,
    sellers_state_df: pl.DataFrame | None,
) -> pl.DataFrame:
    """Исключает listing, чей seller_id имеет is_bankrupt=True."""
    if sellers_state_df is None or sellers_state_df.height == 0:
        return products_df
    bankrupt_ids = (
        sellers_state_df.filter(pl.col(COL_IS_BANKRUPT))
        .select(COL_SELLER_ID)
        .to_series()
        .to_list()
    )
    if not bankrupt_ids:
        return products_df
    return products_df.filter(~pl.col(COL_SELLER_ID).is_in(bankrupt_ids))


def new_bankruptcy_seller_ids(
    prev_state_df: pl.DataFrame,
    next_state_df: pl.DataFrame,
) -> list[int]:
    """Селлеры с переходом is_bankrupt False→True (для system_events в 8.3)."""
    joined = prev_state_df.select(
        COL_SELLER_ID,
        pl.col(COL_IS_BANKRUPT).alias("was_bankrupt"),
    ).join(
        next_state_df.select(
            COL_SELLER_ID,
            pl.col(COL_IS_BANKRUPT).alias("is_bankrupt"),
        ),
        on=COL_SELLER_ID,
        how="inner",
    )
    return (
        joined.filter(~pl.col("was_bankrupt") & pl.col("is_bankrupt"))
        .select(COL_SELLER_ID)
        .to_series()
        .to_list()
    )
