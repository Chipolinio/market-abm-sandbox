# Spec 012, Slice 12.3: per-category ranking + Top-K ∪ Sample-M consideration set.
# RED before: config/ranking.py, simulation/ranking.py, COL_CATEGORY_ID do not exist.
# GREEN after: compute_ranking_scores, build_consideration_indices pure functions.

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import COL_CATEGORY_ID, COL_PRICE, COL_RANKING_SCORE, COL_RATING_VALUE
from market_abm.simulation.ranking import build_consideration_indices, compute_ranking_scores

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_N_CAT = 2
_W1, _W2, _W3 = 0.40, 0.35, 0.25


def _cfg(*, top_k: int = 3, organic_m: int = 1) -> RankingConfig:
    return RankingConfig(w1=_W1, w2=_W2, w3=_W3, top_k=top_k, organic_m=organic_m)


def _products(
    prices: list[float],
    ratings: list[float],
    category_ids: list[int],
    sales_volumes: list[float] | None = None,
) -> pl.DataFrame:
    """Minimal products_df for ranking tests."""
    n = len(prices)
    sv = sales_volumes if sales_volumes is not None else [0.0] * n
    return pl.DataFrame(
        {
            "listing_id": list(range(n)),
            COL_PRICE: prices,
            COL_RATING_VALUE: ratings,
            COL_CATEGORY_ID: category_ids,
            "sales_volume_window": sv,
        }
    ).with_columns(
        pl.col("listing_id").cast(pl.Int32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col("sales_volume_window").cast(pl.Float32),
    )


# ---------------------------------------------------------------------------
# 12.3-T1  scores_computed_per_category — no cross-category Top-K leak
# ---------------------------------------------------------------------------


def test_scores_computed_per_category() -> None:
    """
    Score uses within-category price median.
    Two categories with non-overlapping price ranges must produce independent scores.
    """
    # cat 0: prices [50, 100] → cat_median = 75 → price_score = [1.5, 0.75]
    # cat 1: prices [200, 400] → cat_median = 300 → price_score = [1.5, 0.75]
    df = _products(
        prices=[50.0, 100.0, 200.0, 400.0],
        ratings=[4.0, 4.0, 4.0, 4.0],
        category_ids=[0, 0, 1, 1],
    )
    cfg = _cfg()
    result = compute_ranking_scores(df, cfg)

    assert COL_RANKING_SCORE in result.columns, "ranking_score column must be added"
    scores = result[COL_RANKING_SCORE].to_numpy()

    # Product 0 (cat 0, price 50) vs Product 2 (cat 1, price 200):
    # Both have price = cat_median / 2, same rating, zero sales.
    # Score_0 = w1*4 + w2*(75/50) + w3*log(1) = 1.6 + 0.35*1.5 + 0 = 1.6 + 0.525 = 2.125
    # Score_2 = w1*4 + w2*(300/200) + w3*log(1) = 1.6 + 0.35*1.5 + 0 = 2.125
    assert abs(scores[0] - scores[2]) < 1e-4, (
        "same relative price position within category → same score (per-cat median)"
    )

    # Product 1 (cat 0, price 100) and Product 3 (cat 1, price 400):
    # Both at 2× cat_median → lower price score
    # Score = w1*4 + w2*(median/price) + w3*0 = 1.6 + 0.35*0.75 = 1.8625
    assert abs(scores[1] - scores[3]) < 1e-4

    # Within cat 0: product 0 (cheaper vs median) scores higher than product 1
    assert scores[0] > scores[1], "cheaper-relative-to-median product must rank higher"


def test_scores_include_sales_volume_term() -> None:
    """w3·log(1+sales) lifts a product above equal-price competitor."""
    df = _products(
        prices=[100.0, 100.0],
        ratings=[4.0, 4.0],
        category_ids=[0, 0],
        sales_volumes=[0.0, 50.0],  # product 1 has sales, product 0 does not
    )
    result = compute_ranking_scores(df, _cfg())
    scores = result[COL_RANKING_SCORE].to_numpy()
    assert scores[1] > scores[0], "product with sales volume must rank above zero-sales peer"


# ---------------------------------------------------------------------------
# 12.3-T2  consideration_is_topk_union_samplem
# ---------------------------------------------------------------------------


def test_consideration_is_topk_union_samplem() -> None:
    """
    Returned set contains the Top-K items per category;
    organic items come from residual (non Top-K) rows.
    """
    # 6 products: 3 in cat 0, 3 in cat 1 — all affordable
    # Scores: deliberately assign so we know which are Top-2 per category
    #   cat 0: scores [3.0, 2.0, 1.0] for products [0, 1, 2]
    #   cat 1: scores [2.5, 1.5, 0.5] for products [3, 4, 5]
    scores = np.array([3.0, 2.0, 1.0, 2.5, 1.5, 0.5], dtype=np.float32)
    category_ids = np.array([0, 0, 0, 1, 1, 1], dtype=np.int32)
    affordable_idx = np.arange(6, dtype=np.intp)

    rng = np.random.default_rng(0)
    result = build_consideration_indices(
        affordable_idx,
        category_ids,
        scores,
        top_k=2,
        organic_m=1,
        max_n=100,    # no cap needed
        rng=rng,
    )

    result_set = set(result.tolist())

    # Top-2 cat 0: products 0, 1 — MUST be in set
    assert 0 in result_set, "product 0 (top-1 cat 0) must be in consideration"
    assert 1 in result_set, "product 1 (top-2 cat 0) must be in consideration"

    # Top-2 cat 1: products 3, 4 — MUST be in set
    assert 3 in result_set, "product 3 (top-1 cat 1) must be in consideration"
    assert 4 in result_set, "product 4 (top-2 cat 1) must be in consideration"

    # Organic: product 2 (residual cat 0) or product 5 (residual cat 1)
    # At least one organic per category — both should appear (organic_m=1)
    assert 2 in result_set or 5 in result_set, "organic residual must be sampled"


# ---------------------------------------------------------------------------
# 12.3-T3  organic_sample_deterministic
# ---------------------------------------------------------------------------


def test_organic_sample_deterministic() -> None:
    """Same seed → same organic Sample-M in consideration set."""
    scores = np.array([3.0, 2.0, 1.5, 1.0, 0.8], dtype=np.float32)
    category_ids = np.array([0, 0, 0, 0, 0], dtype=np.int32)
    affordable_idx = np.arange(5, dtype=np.intp)

    def _run(seed: int) -> list[int]:
        rng = np.random.default_rng(seed)
        idx = build_consideration_indices(
            affordable_idx,
            category_ids,
            scores,
            top_k=2,
            organic_m=2,
            max_n=100,
            rng=rng,
        )
        return sorted(idx.tolist())

    assert _run(42) == _run(42), "same seed → identical consideration set"
    # Different seeds may differ (not guaranteed to always differ, but test structure)
    # Just verify same-seed determinism (the core invariant)


# ---------------------------------------------------------------------------
# 12.3-T4  merged_set_capped_by_max_products — multi-cat fixture
# ---------------------------------------------------------------------------


def test_merged_set_capped_by_max_products() -> None:
    """
    |C*| ≤ max_products_per_choice_set always.
    When affordable products span ≥ 2 categories and max_n ≥ n_cats,
    at least 2 categories have ≥ 1 representative in the result.
    """
    # 12 products: 4 per category, 3 categories — all affordable
    n_cats = 3
    n_per_cat = 4
    n = n_cats * n_per_cat
    category_ids = np.repeat(np.arange(n_cats, dtype=np.int32), n_per_cat)
    scores = np.arange(n, dtype=np.float32)[::-1].copy()  # descending
    affordable_idx = np.arange(n, dtype=np.intp)

    max_n = 5   # smaller than 3*4=12; forces cap
    rng = np.random.default_rng(7)
    result = build_consideration_indices(
        affordable_idx,
        category_ids,
        scores,
        top_k=3,
        organic_m=1,
        max_n=max_n,
        rng=rng,
    )

    # Hard cap
    assert len(result) <= max_n, (
        f"consideration set size {len(result)} exceeds max_n={max_n}"
    )

    # Multi-cat representation: with max_n=5 and 3 cats, round-robin should give ≥2 cats
    cats_represented = set(category_ids[result].tolist())
    assert len(cats_represented) >= 2, (
        f"only {len(cats_represented)} categories represented; expected ≥2"
    )


def test_consideration_empty_affordable() -> None:
    """Empty affordable_idx → empty consideration set (no crash)."""
    rng = np.random.default_rng(0)
    result = build_consideration_indices(
        np.array([], dtype=np.intp),
        np.array([], dtype=np.int32),
        np.array([], dtype=np.float32),
        top_k=3,
        organic_m=1,
        max_n=50,
        rng=rng,
    )
    assert result.size == 0
