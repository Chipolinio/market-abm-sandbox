# Spec 012.1 §4 — stock ledger, OOS filter, oversell clip (pure Polars / NumPy).
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_STOCK_UNITS,
)


def filter_in_stock(products_df: pl.DataFrame) -> pl.DataFrame:
    """Keep rows with stock_units > 0. Missing column → ValueError (call only when enabled)."""
    if COL_STOCK_UNITS not in products_df.columns:
        raise ValueError(f"products_df missing required column: {COL_STOCK_UNITS}")
    return products_df.filter(pl.col(COL_STOCK_UNITS) > 0)


def clip_choices_to_stock(
    choices_df: pl.DataFrame,
    products_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Deterministic oversell guard (Spec 012.1 §17 #2 A).

    Per listing keep at most stock_units purchases, ordered by buyer_id ascending.
    Excess purchases become listing_id=null (outside option).
    """
    if COL_STOCK_UNITS not in products_df.columns:
        raise ValueError(f"products_df missing required column: {COL_STOCK_UNITS}")
    if choices_df.height == 0:
        return choices_df

    stock = products_df.select([COL_LISTING_ID, COL_STOCK_UNITS])
    purchases = choices_df.filter(pl.col(COL_LISTING_ID).is_not_null())
    if purchases.height == 0:
        return choices_df

    ranked = purchases.sort([COL_LISTING_ID, COL_BUYER_ID]).with_columns(
        pl.col(COL_LISTING_ID).cum_count().over(COL_LISTING_ID).alias("_rank")
    )
    joined = ranked.join(stock, on=COL_LISTING_ID, how="left")
    # Keep if rank <= stock; else null listing
    kept = joined.with_columns(
        pl.when(pl.col("_rank") <= pl.col(COL_STOCK_UNITS).fill_null(0))
        .then(pl.col(COL_LISTING_ID))
        .otherwise(pl.lit(None).cast(pl.Int32))
        .alias(COL_LISTING_ID)
    ).drop(["_rank", COL_STOCK_UNITS])

    # Re-merge with non-purchase rows (already null listing)
    non_purchases = choices_df.filter(pl.col(COL_LISTING_ID).is_null())
    if non_purchases.height == 0:
        return kept.select(choices_df.columns)
    return pl.concat([kept.select(choices_df.columns), non_purchases], how="vertical")


def apply_stock_sales(
    products_df: pl.DataFrame,
    transactions_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    stock_units := max(0, stock_units - sales_count). Returns new DataFrame.
    Empty tx → clone with unchanged stock.
    """
    if COL_STOCK_UNITS not in products_df.columns:
        raise ValueError(f"products_df missing required column: {COL_STOCK_UNITS}")
    if transactions_df.height == 0:
        return products_df

    sales = (
        transactions_df.group_by(COL_LISTING_ID)
        .len()
        .rename({"len": "_sales"})
    )
    updated = (
        products_df.join(sales, on=COL_LISTING_ID, how="left")
        .with_columns(pl.col("_sales").fill_null(0))
        .with_columns(
            (pl.col(COL_STOCK_UNITS) - pl.col("_sales"))
            .clip(lower_bound=0)
            .cast(pl.Int32)
            .alias(COL_STOCK_UNITS)
        )
        .drop("_sales")
    )
    return updated
