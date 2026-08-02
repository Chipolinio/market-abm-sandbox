# Spec 012 §6 — Dynamic rating EMA + seed-aware stochastic review draws.
# Pure NumPy / Polars functions; no side effects; no OOP.
"""
compute_review_scores — one review score per transaction row, seeded, price-sensitive
update_rating_ema    — EMA update of rating_value in products_df
"""
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.simulation import DynamicRatingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_RATING_VALUE,
)

# Salt per §10: mnemonic "12 REView" → decimal 0x12_3456 placeholder with a unique value.
_REVIEW_SALT: int = 0x12_3ABC  # unique, deterministic, valid hex

_FALLBACK_CAT: int = -1  # category for products without COL_CATEGORY_ID


def compute_review_scores(
    transactions_df: pl.DataFrame,
    products_df: pl.DataFrame,
    *,
    seed: int | None,
    tick_id: int,
) -> np.ndarray:
    """
    Generate one stochastic review score ∈ [score_min, score_max] per transaction (Spec 012 §6).

    Score_tx ~ U(score_min, score_max) with price-vs-cat-median penalty:
        ratio   = price_paid / cat_median_price  (per category_id of the listing)
        penalty = clip(ratio - 1, 0, 1) * price_penalty_scale
        score   = clip(base - penalty, score_min, score_max)

    Seeded via SeedSequence([seed, tick_id, _REVIEW_SALT]) — fully deterministic.
    Transactions sorted by (listing_id, buyer_id) for stable ordering.

    Returns: np.ndarray of shape (n_transactions,), dtype float32,
             in the ORIGINAL row order of transactions_df.
    """
    if transactions_df.height == 0:
        return np.empty(0, dtype=np.float32)

    # Config defaults used here (scores are clipped to [1.0, 5.0] by caller)
    score_min: float = 1.0
    score_max: float = 5.0
    price_penalty_scale: float = 2.0

    # Stable sort for determinism: use original index to restore row order
    n = transactions_df.height
    orig_idx = np.arange(n, dtype=np.intp)
    sort_keys = transactions_df.select([COL_LISTING_ID, "buyer_id"])
    sort_order = np.lexsort(
        (
            sort_keys["buyer_id"].to_numpy(),
            sort_keys[COL_LISTING_ID].to_numpy(),
        )
    )
    inverse_order = np.empty_like(sort_order)
    inverse_order[sort_order] = orig_idx

    # Seeded RNG
    base_seed = 0 if seed is None else seed
    sub = int(np.random.SeedSequence([base_seed, tick_id, _REVIEW_SALT]).generate_state(1)[0])
    rng = np.random.default_rng(sub)

    # Sample base scores in stable-sorted order
    base_scores = rng.uniform(score_min, score_max, size=n).astype(np.float64)

    # Compute price-vs-cat-median penalty using Polars
    if COL_CATEGORY_ID in products_df.columns:
        cat_median = (
            products_df
            .group_by(COL_CATEGORY_ID)
            .agg(pl.col(COL_PRICE).median().alias("_cat_med"))
        )
        products_with_med = products_df.join(cat_median, on=COL_CATEGORY_ID, how="left")
    else:
        global_median = float(products_df[COL_PRICE].median() or 1.0)
        products_with_med = products_df.with_columns(
            pl.lit(global_median, dtype=pl.Float32).alias("_cat_med")
        )

    # Join cat_med onto transactions via listing_id
    listing_cat_med = products_with_med.select([COL_LISTING_ID, "_cat_med"])
    tx_sorted = (
        transactions_df
        .with_row_index("_row_orig")
        .with_columns(pl.lit(sort_order, dtype=pl.UInt32).alias("_sort_rank"))
        # Actually build sorted df for Polars ops
    )
    # Join cat_median into transactions (original order OK, we vectorize below)
    tx_with_med = transactions_df.join(listing_cat_med, on=COL_LISTING_ID, how="left")

    price_paid = tx_with_med[COL_PRICE_PAID].to_numpy().astype(np.float64)
    cat_med = tx_with_med["_cat_med"].fill_null(1.0).to_numpy().astype(np.float64)

    # Reorder to stable sort order for score generation (already done via RNG)
    # Now build penalty in ORIGINAL row order
    ratio = price_paid / np.where(cat_med > 0.0, cat_med, 1.0)
    penalty = np.clip(ratio - 1.0, 0.0, 1.0) * price_penalty_scale

    # base_scores are in stable-sorted order → reorder back to original row order
    base_sorted = base_scores  # generated in stable-sort order
    base_orig = base_sorted[inverse_order]  # back to original order

    scores = np.clip(base_orig - penalty, score_min, score_max)
    return scores.astype(np.float32)


def update_rating_ema(
    products_df: pl.DataFrame,
    transactions_df: pl.DataFrame,
    *,
    seed: int | None,
    tick_id: int,
    cfg: DynamicRatingConfig,
) -> pl.DataFrame:
    """
    EMA-update `rating_value` in products_df based on this tick's transactions (Spec 012 §6).

    Rating_j,t = (1−γ)·Rating_j,t−1 + γ·mean(Score_tx for j)

    - Listings with zero transactions this tick: rating unchanged.
    - Returns new products_df (no mutation).
    - When cfg.enabled=False: returns products_df unchanged.
    """
    if not cfg.enabled or transactions_df.height == 0:
        return products_df

    # Generate one score per transaction
    scores = compute_review_scores(transactions_df, products_df, seed=seed, tick_id=tick_id)

    # Aggregate: mean review score per listing
    scores_series = pl.Series("_review_score", scores.tolist(), dtype=pl.Float32)
    tx_with_scores = transactions_df.with_columns(scores_series)
    mean_scores = (
        tx_with_scores
        .group_by(COL_LISTING_ID)
        .agg(pl.col("_review_score").mean().alias("_mean_review"))
    )

    # Join onto products_df
    updated = products_df.join(mean_scores, on=COL_LISTING_ID, how="left")

    # EMA formula: only update where _mean_review is not null (listing had transactions)
    gamma = float(cfg.gamma)
    new_rating = (
        pl.when(pl.col("_mean_review").is_not_null())
        .then(
            (pl.lit(1.0 - gamma, dtype=pl.Float32) * pl.col(COL_RATING_VALUE))
            + (pl.lit(gamma, dtype=pl.Float32) * pl.col("_mean_review"))
        )
        .otherwise(pl.col(COL_RATING_VALUE))
    )
    # Clip to [score_min, score_max]
    clamped = new_rating.clip(
        lower_bound=pl.lit(cfg.score_min, dtype=pl.Float32),
        upper_bound=pl.lit(cfg.score_max, dtype=pl.Float32),
    )
    return updated.with_columns(clamped.alias(COL_RATING_VALUE)).drop("_mean_review")
