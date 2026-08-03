# Spec 015 §5 — tick welfare / HHI / price moments (pure Polars, no agent classes).
from __future__ import annotations

from typing import Any

import polars as pl

from market_abm.domain.constants import (
    COL_BUDGET,
    COL_BUDGET_EFFECTIVE,
    COL_BUYER_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_UNIT_COST,
)

_HHI_SCALE: float = 10_000.0


def compute_tick_welfare(
    transactions_df: pl.DataFrame,
    buyers_df: pl.DataFrame,
    *,
    platform_fee_rate: float,
) -> dict[str, Any]:
    """
    Aggregate CS proxy / PS / platform profit for one tick.

    CS_proxy = sum(budget_effective - price_paid) per purchase (Spec 015 §19 #5).
    PS = sum(price_paid - unit_cost).
    Platform = sum(price_paid * platform_fee_rate).
    """
    n_tx = int(transactions_df.height)
    if n_tx == 0:
        return {
            "consumer_surplus_proxy": 0.0,
            "producer_surplus": 0.0,
            "platform_profit": 0.0,
            "n_tx": 0,
        }

    fee = float(platform_fee_rate)
    price = transactions_df[COL_PRICE_PAID].cast(pl.Float64)
    cost = transactions_df[COL_UNIT_COST].cast(pl.Float64)
    producer_surplus = float((price - cost).sum())
    platform_profit = float((price * fee).sum())

    budget_col = (
        COL_BUDGET_EFFECTIVE
        if COL_BUDGET_EFFECTIVE in buyers_df.columns
        else COL_BUDGET
    )
    budget_lookup = buyers_df.select(
        pl.col(COL_BUYER_ID),
        pl.col(budget_col).cast(pl.Float64).alias("_budget"),
    )
    joined = transactions_df.join(budget_lookup, on=COL_BUYER_ID, how="left")
    if joined["_budget"].null_count() > 0:
        raise ValueError("buyer budget missing for one or more transactions")
    consumer_surplus_proxy = float(
        (joined["_budget"] - joined[COL_PRICE_PAID].cast(pl.Float64)).sum()
    )

    return {
        "consumer_surplus_proxy": consumer_surplus_proxy,
        "producer_surplus": producer_surplus,
        "platform_profit": platform_profit,
        "n_tx": n_tx,
    }


def compute_tick_hhi(transactions_df: pl.DataFrame) -> float:
    """
    Herfindahl–Hirschman Index on seller revenue shares, FTC scale 0–10000.
    Empty transactions → 0.0 (never NaN) — Spec 015 §19 #6–#7.
    """
    if transactions_df.height == 0:
        return 0.0

    revenue = (
        transactions_df.group_by(COL_SELLER_ID)
        .agg(pl.col(COL_PRICE_PAID).cast(pl.Float64).sum().alias("_rev"))
    )
    total = float(revenue["_rev"].sum())
    if total <= 0.0:
        return 0.0
    shares = revenue["_rev"] / total
    return float((shares * shares).sum() * _HHI_SCALE)


def compute_tick_price_moments(
    prices_df: pl.DataFrame,
    *,
    price_col: str | None = None,
) -> dict[str, float]:
    """
    median_price / price_std from transactions (price_paid) or listings (price).
    Empty → zeros.
    """
    if prices_df.height == 0:
        return {"median_price": 0.0, "price_std": 0.0}

    col = price_col
    if col is None:
        if COL_PRICE_PAID in prices_df.columns:
            col = COL_PRICE_PAID
        elif COL_PRICE in prices_df.columns:
            col = COL_PRICE
        else:
            raise ValueError("prices_df must contain price_paid or price")

    series = prices_df[col].cast(pl.Float64)
    median_price = float(series.median())
    if prices_df.height == 1:
        price_std = 0.0
    else:
        std_val = float(series.std())
        price_std = 0.0 if std_val != std_val else std_val
    return {"median_price": median_price, "price_std": price_std}


def build_tick_metrics_row(
    *,
    tick_id: int,
    transactions_df: pl.DataFrame,
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    platform_fee_rate: float,
) -> dict[str, Any]:
    """One tick_metrics.parquet row — welfare + HHI + price moments + gmv."""
    welfare = compute_tick_welfare(
        transactions_df,
        buyers_df,
        platform_fee_rate=platform_fee_rate,
    )
    if transactions_df.height > 0:
        moments = compute_tick_price_moments(transactions_df)
    else:
        moments = compute_tick_price_moments(products_df)
    gmv = (
        float(transactions_df[COL_PRICE_PAID].cast(pl.Float64).sum())
        if transactions_df.height
        else 0.0
    )
    # Shelf mean: detects ML share even when purchases monopolize one listing.
    mean_listing_price = (
        float(products_df[COL_PRICE].cast(pl.Float64).mean())
        if products_df.height and COL_PRICE in products_df.columns
        else 0.0
    )
    return {
        "tick_id": int(tick_id),
        "median_price": moments["median_price"],
        "mean_listing_price": mean_listing_price,
        "price_std": moments["price_std"],
        "hhi": compute_tick_hhi(transactions_df),
        "consumer_surplus_proxy": welfare["consumer_surplus_proxy"],
        "producer_surplus": welfare["producer_surplus"],
        "platform_profit": welfare["platform_profit"],
        "gmv": gmv,
        "n_tx": welfare["n_tx"],
    }
