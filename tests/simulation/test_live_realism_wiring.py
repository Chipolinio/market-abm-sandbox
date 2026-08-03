# Spec 013, Slice 13.1: live wire ranking + consideration into step hot path.
# RED before: step does not call compute_ranking_scores / does not pass arrays to choice.
# GREEN after: one ranking precompute/tick → category_ids + ranking_scores in choice;
#              products_next carries ranking_score (extra col preserved).

from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.ranking import RankingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_CATEGORY_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_RANKING_SCORE,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.choice import choose_listings_for_all_buyers
from market_abm.simulation.ranking import compute_ranking_scores
from market_abm.simulation.step import step

_SEED = 42
_TICK = 1
_N_BUYERS = 80


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _ranking_cfg() -> RankingConfig:
    """Tight Top-K, no organic sample → strong divergence from uniform rng.choice."""
    return RankingConfig(
        w1=0.40,
        w2=0.35,
        w3=0.25,
        top_k=2,
        organic_m=0,
        n_categories=2,
    )


def _choice_cfg() -> ChoiceModelConfig:
    return ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=20,
        outside_utility_bias=-100.0,
        ranking=_ranking_cfg(),
    )


def _step_cfg(**kwargs: object) -> SimulationStepConfig:
    defaults: dict[str, object] = {
        "tick_id": _TICK,
        "seed": _SEED,
        "choice": _choice_cfg(),
        "repricing": RepricingConfig.default_market(),
    }
    defaults.update(kwargs)
    return SimulationStepConfig(**defaults)


def _buyers_df(n: int = _N_BUYERS) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [500.0] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
    )


def _sellers_df(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            "capital": [10_000.0] * n,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _asymmetric_products() -> pl.DataFrame:
    """
    Two categories × 6 listings. Cat 0: high rating / low price → high score.
    Cat 1: low rating / high price → low score. All affordable for budget=500.
    """
    # listing 0..5 → cat 0; 6..11 → cat 1
    prices = [40.0, 45.0, 50.0, 80.0, 90.0, 100.0] + [
        120.0,
        130.0,
        140.0,
        150.0,
        160.0,
        170.0,
    ]
    ratings = [5.0, 4.8, 4.5, 3.0, 2.5, 2.0] + [2.0, 1.8, 1.5, 1.2, 1.0, 1.0]
    cats = [0] * 6 + [1] * 6
    n = len(prices)
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: ratings,
            COL_CATEGORY_ID: cats,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
    )


def _purchase_listing_ids(choices_or_tx: pl.DataFrame) -> list[int]:
    """Non-null listing_id list (order-preserving) from choices or transactions."""
    col = choices_or_tx[COL_LISTING_ID]
    return [int(x) for x in col.to_list() if x is not None]


def _choice_arrays(
    products: pl.DataFrame,
    cfg: ChoiceModelConfig,
) -> tuple[pl.DataFrame, np.ndarray, np.ndarray]:
    ranked = compute_ranking_scores(products, cfg.ranking, sales_volume_by_listing=None)
    category_ids = ranked[COL_CATEGORY_ID].to_numpy()
    ranking_scores = ranked[COL_RANKING_SCORE].to_numpy()
    return ranked, category_ids, ranking_scores


# ---------------------------------------------------------------------------
# 13.1-T1  live_step_attaches_ranking_score
# ---------------------------------------------------------------------------


def test_live_step_attaches_ranking_score() -> None:
    """
    After live step with category_id present, products_next must carry ranking_score
    (Spec 013 §4.1 / §13.1-T1). Cold-start sales → zeros inside ranking.
    """
    buyers = _buyers_df()
    products = _asymmetric_products()
    sellers = _sellers_df(products.height)
    cfg = _step_cfg()

    products_next, _tx, _sellers_state = step(buyers, sellers, products, cfg)

    assert COL_CATEGORY_ID in products_next.columns, "category_id must survive step"
    assert COL_RANKING_SCORE in products_next.columns, (
        "ranking_score must be attached by live step ranking precompute"
    )
    scores = products_next[COL_RANKING_SCORE].to_numpy()
    assert len(scores) == products.height
    assert np.isfinite(scores).all(), "ranking_score must be finite"
    # Asymmetric fixture: best cat-0 listing scores above weakest cat-1 listing
    by_id = dict(
        zip(
            products_next[COL_LISTING_ID].to_list(),
            scores.tolist(),
            strict=True,
        )
    )
    assert by_id[0] > by_id[11], (
        "high-rating/low-price listing must outrank weak peer after live ranking"
    )


# ---------------------------------------------------------------------------
# 13.1-T2  live_consideration_not_pure_random
# ---------------------------------------------------------------------------


def test_live_consideration_not_pure_random() -> None:
    """
    Multi-cat: live step choice distribution must match wired ranking path and
    differ from legacy rng.choice (no arrays), same seed (Spec 013 §13.1-T2).
    """
    buyers = _buyers_df()
    products = _asymmetric_products()
    sellers = _sellers_df(products.height)
    cfg = _step_cfg()
    choice_cfg = cfg.choice

    ranked, category_ids, ranking_scores = _choice_arrays(products, choice_cfg)

    wired = choose_listings_for_all_buyers(
        buyers,
        ranked,
        seed=_SEED,
        config=choice_cfg,
        category_ids=category_ids,
        ranking_scores=ranking_scores,
    )
    legacy = choose_listings_for_all_buyers(
        buyers,
        ranked,
        seed=_SEED,
        config=choice_cfg,
    )
    wired_ids = _purchase_listing_ids(wired)
    legacy_ids = _purchase_listing_ids(legacy)

    assert wired_ids, "fixture must produce purchases on wired path"
    assert legacy_ids, "fixture must produce purchases on legacy path"
    assert wired_ids != legacy_ids, (
        "fixture sanity: Top-K consideration must diverge from pure random affordable"
    )

    _products_next, tx, _sellers_state = step(buyers, sellers, products, cfg)
    live_ids = _purchase_listing_ids(tx)

    assert live_ids, "live step must produce purchases"
    assert live_ids != legacy_ids, (
        "live step must not follow legacy rng.choice path (ranking arrays required)"
    )
    assert live_ids == wired_ids, (
        "live step choice multiset must match explicit wired ranking path (same seed)"
    )
