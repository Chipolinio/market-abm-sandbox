# Spec 012.1 §4–§6 — stock ledger, OOS, pressure, replenishment (prepaid + holding).
from __future__ import annotations

import polars as pl

from market_abm.config.inventory import InventoryPricingConfig, ReplenishmentConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_INBOUND_ETA_TICKS,
    COL_INBOUND_UNIT_COST,
    COL_INBOUND_UNITS,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_SELLER_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
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


def ensure_inbound_columns(products_df: pl.DataFrame) -> pl.DataFrame:
    """Add inbound_* columns with zeros if missing."""
    df = products_df
    if COL_INBOUND_UNITS not in df.columns:
        df = df.with_columns(pl.lit(0, dtype=pl.Int32).alias(COL_INBOUND_UNITS))
    if COL_INBOUND_ETA_TICKS not in df.columns:
        df = df.with_columns(pl.lit(0, dtype=pl.Int32).alias(COL_INBOUND_ETA_TICKS))
    if COL_INBOUND_UNIT_COST not in df.columns:
        df = df.with_columns(pl.lit(0.0, dtype=pl.Float32).alias(COL_INBOUND_UNIT_COST))
    return df


def apply_bootstrap_stock_prepaid(
    sellers_state_df: pl.DataFrame,
    products_df: pl.DataFrame,
) -> pl.DataFrame:
    """
    Mode C: prepaid COGS for bootstrap stock at init (Spec 012.1 §4.2 / §6.3).
    working_capital -= Σ(stock_units · unit_cost) per seller.
    """
    if COL_STOCK_UNITS not in products_df.columns:
        raise ValueError(f"products_df missing required column: {COL_STOCK_UNITS}")
    prepaid = (
        products_df.group_by(COL_SELLER_ID)
        .agg(
            (
                pl.col(COL_STOCK_UNITS).cast(pl.Float32)
                * pl.col(COL_UNIT_COST).cast(pl.Float32)
            )
            .sum()
            .alias("_prepaid")
        )
    )
    return (
        sellers_state_df.join(prepaid, on=COL_SELLER_ID, how="left")
        .with_columns(pl.col("_prepaid").fill_null(0.0).cast(pl.Float32))
        .with_columns(
            (pl.col(COL_WORKING_CAPITAL) - pl.col("_prepaid"))
            .cast(pl.Float32)
            .alias(COL_WORKING_CAPITAL)
        )
        .drop("_prepaid")
    )


def compute_holding_by_seller(
    products_df: pl.DataFrame,
    *,
    holding_cost_per_unit_tick: float,
) -> pl.DataFrame:
    """Per-seller holding = holding_cost_per_unit_tick * sum(stock_units)."""
    if COL_STOCK_UNITS not in products_df.columns or products_df.height == 0:
        return pl.DataFrame(
            {
                COL_SELLER_ID: pl.Series([], dtype=pl.Int32),
                "_holding": pl.Series([], dtype=pl.Float32),
            }
        )
    rate = float(holding_cost_per_unit_tick)
    return (
        products_df.group_by(COL_SELLER_ID)
        .agg(
            (pl.col(COL_STOCK_UNITS).cast(pl.Float32).sum() * pl.lit(rate, dtype=pl.Float32))
            .alias("_holding")
        )
    )


def advance_replenishment(
    products_df: pl.DataFrame,
    sellers_state_df: pl.DataFrame,
    cfg: ReplenishmentConfig,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """
    Spec 012.1 §6: arrive inbound → maybe reorder with prepaid capital.

    Order (per tick):
      1) eta -= 1 for open inbound; on eta<=0 add to stock and clear inbound
      2) if inbound==0 and stock<=reorder_point and seller not bankrupt and capital>=cost:
            place order (inbound, eta=lead_time); capital -= qty*unit_cost
    """
    if not cfg.enabled:
        return products_df, sellers_state_df

    df = ensure_inbound_columns(products_df)

    # --- arrive ---
    eta_next = pl.col(COL_INBOUND_ETA_TICKS) - pl.lit(1, dtype=pl.Int32)
    arriving = (pl.col(COL_INBOUND_UNITS) > 0) & (eta_next <= 0)
    in_flight = (pl.col(COL_INBOUND_UNITS) > 0) & (eta_next > 0)

    stock_after = (
        pl.when(arriving)
        .then(pl.col(COL_STOCK_UNITS) + pl.col(COL_INBOUND_UNITS))
        .otherwise(pl.col(COL_STOCK_UNITS))
        .cast(pl.Int32)
    )
    inbound_after_arrive = (
        pl.when(arriving)
        .then(pl.lit(0, dtype=pl.Int32))
        .when(in_flight)
        .then(pl.col(COL_INBOUND_UNITS))
        .otherwise(pl.lit(0, dtype=pl.Int32))
    )
    eta_after_arrive = (
        pl.when(arriving)
        .then(pl.lit(0, dtype=pl.Int32))
        .when(in_flight)
        .then(eta_next.cast(pl.Int32))
        .otherwise(pl.lit(0, dtype=pl.Int32))
    )
    inbound_cost_after = (
        pl.when(arriving | (pl.col(COL_INBOUND_UNITS) == 0))
        .then(pl.lit(0.0, dtype=pl.Float32))
        .otherwise(pl.col(COL_INBOUND_UNIT_COST))
    )

    df = df.with_columns(
        stock_after.alias(COL_STOCK_UNITS),
        inbound_after_arrive.alias(COL_INBOUND_UNITS),
        eta_after_arrive.alias(COL_INBOUND_ETA_TICKS),
        inbound_cost_after.alias(COL_INBOUND_UNIT_COST),
    )

    # --- reorder ---
    capital_map = {
        int(r[COL_SELLER_ID]): float(r[COL_WORKING_CAPITAL])
        for r in sellers_state_df.iter_rows(named=True)
    }
    bankrupt = {
        int(r[COL_SELLER_ID])
        for r in sellers_state_df.filter(pl.col(COL_IS_BANKRUPT)).iter_rows(named=True)
    }

    new_inbound: list[int] = []
    new_eta: list[int] = []
    new_cost: list[float] = []
    order_cost_by_seller: dict[int, float] = {}

    for row in df.iter_rows(named=True):
        sid = int(row[COL_SELLER_ID])
        stock = int(row[COL_STOCK_UNITS])
        inbound = int(row[COL_INBOUND_UNITS])
        unit_cost = float(row[COL_UNIT_COST])
        if (
            inbound == 0
            and stock <= int(cfg.reorder_point)
            and sid not in bankrupt
        ):
            qty = int(cfg.reorder_quantity)
            cost = float(qty) * unit_cost
            cap = capital_map.get(sid, 0.0) - order_cost_by_seller.get(sid, 0.0)
            if cap >= cost:
                new_inbound.append(qty)
                new_eta.append(int(cfg.lead_time_ticks))
                new_cost.append(unit_cost)
                order_cost_by_seller[sid] = order_cost_by_seller.get(sid, 0.0) + cost
                continue
        new_inbound.append(inbound)
        new_eta.append(int(row[COL_INBOUND_ETA_TICKS]))
        new_cost.append(float(row[COL_INBOUND_UNIT_COST]))

    df = df.with_columns(
        pl.Series(COL_INBOUND_UNITS, new_inbound, dtype=pl.Int32),
        pl.Series(COL_INBOUND_ETA_TICKS, new_eta, dtype=pl.Int32),
        pl.Series(COL_INBOUND_UNIT_COST, new_cost, dtype=pl.Float32),
    )

    if not order_cost_by_seller:
        return df, sellers_state_df

    costs = pl.DataFrame(
        {
            COL_SELLER_ID: list(order_cost_by_seller.keys()),
            "_order_cost": list(order_cost_by_seller.values()),
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col("_order_cost").cast(pl.Float32),
    )
    state_next = (
        sellers_state_df.join(costs, on=COL_SELLER_ID, how="left")
        .with_columns(pl.col("_order_cost").fill_null(0.0).cast(pl.Float32))
        .with_columns(
            (pl.col(COL_WORKING_CAPITAL) - pl.col("_order_cost"))
            .cast(pl.Float32)
            .alias(COL_WORKING_CAPITAL)
        )
        .drop("_order_cost")
    )
    return df, state_next
