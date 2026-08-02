# Spec 012 §4.1–4.2 — per-category ranking score and consideration set.
# Hot path contract: compute_ranking_scores called once/tick (Polars vectorized);
# build_consideration_indices called per-buyer (pure NumPy, no Polars in inner loop).
"""
compute_ranking_scores  — Score_j = w1·Rating_j + w2·(P_cat_median/P_j) + w3·log(1+Sales_j)
build_consideration_indices — Top-K(cat) ∪ Sample-M(residual|cat), merge-capped to max_n
"""
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_PRICE,
    COL_RANKING_SCORE,
    COL_RATING_VALUE,
)

_SALES_COL: str = "sales_volume_window"


def compute_ranking_scores(
    products_df: pl.DataFrame,
    cfg: RankingConfig,
    *,
    sales_volume_by_listing: dict[int, float] | None = None,
) -> pl.DataFrame:
    """
    Add / replace `ranking_score` column on products_df (Polars vectorized, one pass).

    Score_j = w1·Rating_j + w2·(P_cat_median / P_j) + w3·log(1 + SalesVolume_j)

    Computed **strictly per category_id** — no cross-category influence.
    Returns new DataFrame (does not mutate input).
    """
    if COL_CATEGORY_ID not in products_df.columns:
        # Fallback for legacy products without category: uniform score = rating only
        scores = (cfg.w1 * products_df[COL_RATING_VALUE]).cast(pl.Float32)
        return products_df.with_columns(scores.alias(COL_RANKING_SCORE))

    # Resolve sales volume: use column if present, else lookup dict, else zeros
    if _SALES_COL in products_df.columns:
        sales = products_df[_SALES_COL]
    elif sales_volume_by_listing is not None:
        listing_ids = products_df["listing_id"].to_list()
        sales = pl.Series(
            _SALES_COL,
            [float(sales_volume_by_listing.get(lid, 0.0)) for lid in listing_ids],
            dtype=pl.Float32,
        )
    else:
        sales = pl.Series(_SALES_COL, [0.0] * products_df.height, dtype=pl.Float32)

    df = products_df.with_columns(sales.alias(_SALES_COL))

    # Per-category price median using Polars group_by (vectorized, no Python loop)
    cat_median = (
        df.group_by(COL_CATEGORY_ID)
        .agg(pl.col(COL_PRICE).median().alias("_p_cat_median"))
    )
    df = df.join(cat_median, on=COL_CATEGORY_ID, how="left")

    # Compute score components
    df = df.with_columns(
        (
            cfg.w1 * pl.col(COL_RATING_VALUE)
            + cfg.w2 * (pl.col("_p_cat_median") / pl.col(COL_PRICE).clip(lower_bound=1e-6))
            + cfg.w3 * (1.0 + pl.col(_SALES_COL)).log(base=float(np.e))
        )
        .cast(pl.Float32)
        .alias(COL_RANKING_SCORE)
    )

    # Drop helper columns; preserve original + ranking_score
    drop = ["_p_cat_median"]
    if _SALES_COL not in products_df.columns:
        drop.append(_SALES_COL)
    return df.drop(drop)


def build_consideration_indices(
    affordable_idx: np.ndarray,
    category_ids: np.ndarray,
    scores: np.ndarray,
    *,
    top_k: int,
    organic_m: int,
    max_n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Pure NumPy hot path — returns row indices into products array, len ≤ max_n.

    Algorithm (Spec 012 §4.2 / §4.2.1):
      Per category in affordable_idx:
        TopK_cat  = top_k indices by score (descending)
        Residual_cat = remaining indices
        Organic_cat  = Sample-M from residual (seed-aware)
        C_cat = TopK_cat ∪ Organic_cat
      C_raw = ⋃ C_cat
      If |C_raw| ≤ max_n: return C_raw (mapped to product row indices)
      Else: round-robin from Top-K across categories, then fill with organic.

    Args:
        affordable_idx: row indices into products array (len n_affordable)
        category_ids:   shape (n_products,) — category per product row
        scores:         shape (n_products,) — ranking_score per product row
        top_k, organic_m, max_n: RankingConfig-derived parameters
        rng: seeded Generator (caller provides salt per §10)

    Returns:
        1-D int ndarray of product row indices, len ≤ max_n.
    """
    if affordable_idx.size == 0:
        return affordable_idx.copy()

    # Slice category + score for affordable subset
    aff_cats = category_ids[affordable_idx]
    aff_scores = scores[affordable_idx]
    unique_cats = np.unique(aff_cats)

    # Per-category Top-K and residual (as local positions within affordable_idx)
    topk_by_cat: dict[int, np.ndarray] = {}
    residual_by_cat: dict[int, np.ndarray] = {}

    for cat in unique_cats:
        cat = int(cat)
        mask = aff_cats == cat
        local_pos = np.flatnonzero(mask)            # positions in affordable_idx
        cat_scores = aff_scores[local_pos]
        order = np.argsort(-cat_scores, kind="stable")
        sorted_pos = local_pos[order]
        k = min(top_k, len(sorted_pos))
        topk_by_cat[cat] = sorted_pos[:k]
        residual_by_cat[cat] = sorted_pos[k:]

    # Organic Sample-M per category from residual
    organic_by_cat: dict[int, np.ndarray] = {}
    for cat in unique_cats:
        cat = int(cat)
        res = residual_by_cat[cat]
        if res.size > 0 and organic_m > 0:
            m = min(organic_m, res.size)
            organic_by_cat[cat] = rng.choice(res, size=m, replace=False)
        else:
            organic_by_cat[cat] = np.array([], dtype=np.intp)

    # Build C_raw per category = Top-K ∪ Organic
    c_cat: dict[int, np.ndarray] = {}
    for cat in unique_cats:
        cat = int(cat)
        c_cat[cat] = np.unique(
            np.concatenate([topk_by_cat[cat], organic_by_cat[cat]])
        )

    # Flatten C_raw
    all_parts = [c_cat[int(c)] for c in unique_cats]
    c_raw_local = np.unique(np.concatenate(all_parts)) if all_parts else np.array([], dtype=np.intp)

    if c_raw_local.size <= max_n:
        return affordable_idx[c_raw_local]

    # --- Cap: round-robin Top-K, then organic fill ---
    result_local: list[int] = []
    remaining = max_n

    # Round-robin from Top-K queues (one item per category per round)
    queues = {int(c): list(topk_by_cat[int(c)]) for c in unique_cats}
    while remaining > 0:
        added = False
        for cat in unique_cats:
            cat = int(cat)
            if queues[cat] and remaining > 0:
                result_local.append(queues[cat].pop(0))
                remaining -= 1
                added = True
        if not added:
            break

    # Fill remaining slots with organic (deduplicated)
    if remaining > 0:
        already = set(result_local)
        organic_pool = [
            int(i)
            for cat in unique_cats
            for i in organic_by_cat[int(cat)]
            if int(i) not in already
        ]
        m = min(remaining, len(organic_pool))
        if m > 0:
            chosen = rng.choice(organic_pool, size=m, replace=False)
            result_local.extend(int(x) for x in chosen)

    result_arr = np.array(result_local, dtype=np.intp)
    return affordable_idx[np.unique(result_arr)]
