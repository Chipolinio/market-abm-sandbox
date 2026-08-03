# Spec 013 §5 — resolve reference price + advance rolling realism windows.
# Pure functions; no in-place mutation of SimulationContext.
from __future__ import annotations

from dataclasses import replace

import numpy as np
import polars as pl

from market_abm.config.simulation import ReferencePriceConfig
from market_abm.domain.constants import COL_LISTING_ID, COL_PRICE, COL_PRICE_PAID
from market_abm.simulation.context import SimulationContext

# Spec 013 §16 / Spec 012 §5.2.1
DEFAULT_N_TX_MIN: int = 5
DEFAULT_SALES_WINDOW_TICKS: int = 20

# sales_counts_ring: tuple of per-tick (listing_id, count) tuples
SalesTickCounts = tuple[tuple[int, int], ...]


def resolve_reference_price(
    ctx: SimulationContext | None,
    products_df: pl.DataFrame,
    cfg: ReferencePriceConfig,
) -> float | None:
    """
    Resolve scalar ref_price for MNL penalty (Spec 013 §5.1).

    enabled=False → None (choice noop).
    Non-empty ctx.tx_p50_window → median of window.
    Cold-start → median(listing price); empty/invalid products → None.
    """
    if not cfg.enabled:
        return None
    if ctx is not None and len(ctx.tx_p50_window) > 0:
        return float(np.median(np.asarray(ctx.tx_p50_window, dtype=np.float64)))
    if products_df.height == 0 or COL_PRICE not in products_df.columns:
        return None
    med = products_df[COL_PRICE].median()
    return float(med) if med is not None else None


def aggregate_sales_volume_by_listing(
    ctx: SimulationContext,
) -> dict[int, float] | None:
    """Sum sales counts over ctx.sales_counts_ring; None if ring empty (cold-start)."""
    if not ctx.sales_counts_ring:
        return None
    agg: dict[int, float] = {}
    for tick_counts in ctx.sales_counts_ring:
        for listing_id, count in tick_counts:
            agg[int(listing_id)] = agg.get(int(listing_id), 0.0) + float(count)
    return agg


def _tick_sales_counts(transactions_df: pl.DataFrame) -> SalesTickCounts:
    if transactions_df.height == 0 or COL_LISTING_ID not in transactions_df.columns:
        return ()
    counts = (
        transactions_df.group_by(COL_LISTING_ID)
        .len()
        .rename({"len": "sales_count"})
        .sort(COL_LISTING_ID)
    )
    return tuple(
        (int(lid), int(cnt))
        for lid, cnt in zip(
            counts[COL_LISTING_ID].to_list(),
            counts["sales_count"].to_list(),
            strict=True,
        )
    )


def _listing_price_median(products_df: pl.DataFrame) -> float | None:
    if products_df.height == 0 or COL_PRICE not in products_df.columns:
        return None
    med = products_df[COL_PRICE].median()
    return float(med) if med is not None else None


def advance_realism_windows(
    ctx: SimulationContext,
    transactions_df: pl.DataFrame,
    products_df: pl.DataFrame,
    *,
    ref_cfg: ReferencePriceConfig,
    sales_window_ticks: int = DEFAULT_SALES_WINDOW_TICKS,
    n_tx_min: int = DEFAULT_N_TX_MIN,
) -> SimulationContext:
    """
    Append tick p50_tx (or listing median fallback) + sales counts; trim rings.
    Returns a new SimulationContext (replace); never mutates ctx.
    """
    listing_med = _listing_price_median(products_df)
    if transactions_df.height >= n_tx_min and COL_PRICE_PAID in transactions_df.columns:
        tx_med = transactions_df[COL_PRICE_PAID].median()
        tick_p50 = float(tx_med) if tx_med is not None else listing_med
    else:
        tick_p50 = listing_med

    new_tx_window = ctx.tx_p50_window
    if tick_p50 is not None:
        maxlen = int(ref_cfg.window_ticks)
        new_tx_window = (*ctx.tx_p50_window, float(tick_p50))[-maxlen:]

    tick_sales = _tick_sales_counts(transactions_df)
    new_sales_ring = (*ctx.sales_counts_ring, tick_sales)[-int(sales_window_ticks) :]

    return replace(
        ctx,
        tx_p50_window=new_tx_window,
        sales_counts_ring=new_sales_ring,
    )
