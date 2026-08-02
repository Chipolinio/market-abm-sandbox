# Назначение файла: p50 transaction price metrics with sparse-tx fallback (Slice 12.6, Spec 012 §5.2).
from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
import polars as pl

from market_abm.domain.constants import COL_PRICE_PAID

# Spec 012 §16.3 defaults
_N_TX_MIN_DEFAULT: int = 5
_W_PRE_DEFAULT: int = 20
_W_POST_DEFAULT: int = 40

P50Source = Literal["transaction", "listing_fallback", "mixed"]


def compute_tick_p50(
    transactions_df: pl.DataFrame,
    *,
    n_tx_min: int = _N_TX_MIN_DEFAULT,
    listing_p50: float,
) -> tuple[float, P50Source]:
    """
    Computes p50 price for a single tick using sparse-tx fallback (Spec 012 §5.2.1).

    Returns (p50_value, source) where source ∈ {"transaction", "listing_fallback"}.
    Uses median(price_paid) when n_tx >= n_tx_min, otherwise falls back to listing_p50.
    """
    if transactions_df.height >= n_tx_min:
        median_val = transactions_df[COL_PRICE_PAID].median()
        return float(median_val) if median_val is not None else listing_p50, "transaction"
    return listing_p50, "listing_fallback"


def compute_p50_drop(
    transactions_by_tick: Sequence[pl.DataFrame],
    listing_p50_by_tick: Sequence[float],
    *,
    shock_tick: int,
    w_pre: int = _W_PRE_DEFAULT,
    w_post: int = _W_POST_DEFAULT,
    n_tx_min: int = _N_TX_MIN_DEFAULT,
) -> tuple[float, P50Source]:
    """
    Computes the p50 price drop around a shock tick (Spec 012 §5.2).

    Pre-window:  [shock_tick - w_pre, shock_tick)
    Post-window: [shock_tick,          shock_tick + w_post)

    drop = (pre_mean - trough) / pre_mean

    For each tick, uses compute_tick_p50() which falls back to listing_p50 when sparse.

    Returns:
        (drop_fraction, p50_metric_source)
        p50_metric_source ∈ {"transaction", "listing_fallback", "mixed"}
    """
    n = len(transactions_by_tick)
    pre_start = max(0, shock_tick - w_pre)
    pre_end = min(n, shock_tick)
    post_start = min(n, shock_tick)
    post_end = min(n, shock_tick + w_post)

    pre_values: list[float] = []
    pre_sources: list[P50Source] = []
    for t in range(pre_start, pre_end):
        val, src = compute_tick_p50(
            transactions_by_tick[t],
            n_tx_min=n_tx_min,
            listing_p50=listing_p50_by_tick[t],
        )
        pre_values.append(val)
        pre_sources.append(src)

    post_values: list[float] = []
    post_sources: list[P50Source] = []
    for t in range(post_start, post_end):
        val, src = compute_tick_p50(
            transactions_by_tick[t],
            n_tx_min=n_tx_min,
            listing_p50=listing_p50_by_tick[t],
        )
        post_values.append(val)
        post_sources.append(src)

    if not pre_values or not post_values:
        return 0.0, "transaction"

    pre_mean = float(np.mean(pre_values))
    trough = float(np.min(post_values))

    drop = (pre_mean - trough) / pre_mean if pre_mean > 0.0 else 0.0

    all_sources: set[P50Source] = set(pre_sources) | set(post_sources)
    if "transaction" in all_sources and "listing_fallback" in all_sources:
        source: P50Source = "mixed"
    elif "listing_fallback" in all_sources:
        source = "listing_fallback"
    else:
        source = "transaction"

    return drop, source
