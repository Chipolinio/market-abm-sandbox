# Spec 012.1 §4–§5 — stock ledger, OOS filter, oversell clip, inventory pressure.
from __future__ import annotations

import polars as pl

from market_abm.config.inventory import InventoryPricingConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
)

COL_INVENTORY_PRESSURE: str = "inventory_pressure"


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
    kept = joined.with_columns(
        pl.when(pl.col("_rank") <= pl.col(COL_STOCK_UNITS).fill_null(0))
        .then(pl.col(COL_LISTING_ID))
        .otherwise(pl.lit(None).cast(pl.Int32))
        .alias(COL_LISTING_ID)
    ).drop(["_rank", COL_STOCK_UNITS])

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
    Empty tx → unchanged stock.
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
    return (
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


def compute_inventory_pressure(
    products_df: pl.DataFrame,
    cfg: InventoryPricingConfig,
    *,
    sell_through_by_listing: dict[int, float] | None = None,
) -> pl.DataFrame:
    """
    inventory_pressure ∈ [-1, +1] (Spec 012.1 §5.1).

    cover_ratio = stock / max(target, 1)
    pressure = clip(α·(cover_ratio − 1) − β·sell_through_gap, -1, 1)

    sell_through_gap = 0 when sell_through_by_listing is None (v1 default).
    Missing stock_target → target := stock_units (cover term ≈ 0).
    """
    if COL_STOCK_UNITS not in products_df.columns:
        raise ValueError(f"products_df missing required column: {COL_STOCK_UNITS}")

    df = products_df
    if COL_STOCK_TARGET not in df.columns:
        df = df.with_columns(pl.col(COL_STOCK_UNITS).alias(COL_STOCK_TARGET))

    if sell_through_by_listing is not None:
        lids = df[COL_LISTING_ID].to_list()
        df = df.with_columns(
            pl.Series(
                "_sell_through",
                [float(sell_through_by_listing.get(int(lid), 0.0)) for lid in lids],
                dtype=pl.Float32,
            )
        )
        sell_gap = pl.col("_sell_through")
    else:
        sell_gap = pl.lit(0.0, dtype=pl.Float32)

    target = pl.col(COL_STOCK_TARGET).cast(pl.Float32).clip(lower_bound=1.0)
    cover = pl.col(COL_STOCK_UNITS).cast(pl.Float32) / target
    alpha = pl.lit(float(cfg.pressure_alpha), dtype=pl.Float32)
    beta = pl.lit(float(cfg.pressure_beta), dtype=pl.Float32)
    pressure = (alpha * (cover - pl.lit(1.0, dtype=pl.Float32)) - beta * sell_gap).clip(
        -1.0, 1.0
    )
    out = df.with_columns(pressure.cast(pl.Float32).alias(COL_INVENTORY_PRESSURE))
    if "_sell_through" in out.columns:
        out = out.drop("_sell_through")
    return out.select([COL_LISTING_ID, COL_INVENTORY_PRESSURE])
