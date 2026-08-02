# Spec 012, Slice 12.5: Dynamic rating EMA + seed-aware review draws.
# RED before: DynamicRatingConfig not in config/simulation.py;
#             simulation/rating.py does not exist.
# GREEN after: compute_review_scores (seeded, price-sensitive) +
#              update_rating_ema (EMA per listing, noop for no-tx).

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.simulation import DynamicRatingConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_CATEGORY_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
)
from market_abm.simulation.rating import compute_review_scores, update_rating_ema

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_SEED = 42
_TICK = 0


def _products(
    n: int,
    *,
    base_rating: float = 4.0,
    prices: list[float] | None = None,
    category_ids: list[int] | None = None,
) -> pl.DataFrame:
    prices_ = prices if prices is not None else [100.0] * n
    cats = category_ids if category_ids is not None else [0] * n
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [30.0] * n,
            COL_PRICE: prices_,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [base_rating] * n,
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


def _tx(
    listing_ids: list[int],
    prices_paid: list[float] | None = None,
    *,
    tick_id: int = 0,
) -> pl.DataFrame:
    n = len(listing_ids)
    prices_ = prices_paid if prices_paid is not None else [100.0] * n
    return pl.DataFrame(
        {
            COL_TICK_ID: [tick_id] * n,
            COL_BUYER_ID: list(range(n)),
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: listing_ids,
            COL_PRICE_PAID: prices_,
            COL_UNIT_COST: [30.0] * n,
            COL_GROSS_MARGIN: [p - 30.0 for p in prices_],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )


def _cfg(**kw) -> DynamicRatingConfig:
    return DynamicRatingConfig(**kw)


# ---------------------------------------------------------------------------
# 12.5-T1a  ema_moves_after_transactions — listing with tx changes rating
# ---------------------------------------------------------------------------


def test_ema_moves_after_transactions() -> None:
    """
    Listing that received transactions this tick must have its rating updated via EMA.
    Listing with zero transactions must remain unchanged.
    """
    products = _products(2, base_rating=4.0)
    transactions = _tx(listing_ids=[0])   # only listing 0 gets a review

    cfg = _cfg()
    result = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=cfg)

    ratings_before = products[COL_RATING_VALUE].to_numpy()
    ratings_after = result[COL_RATING_VALUE].to_numpy()

    # Listing 0: had a transaction → rating must change
    assert ratings_after[0] != ratings_before[0], (
        "listing with transaction should have updated rating"
    )
    # Listing 1: no transaction → rating unchanged
    assert ratings_after[1] == pytest.approx(ratings_before[1]), (
        "listing without transaction should keep its rating"
    )


def test_ema_output_rating_in_valid_range() -> None:
    """All ratings after EMA update stay within [score_min, score_max]."""
    products = _products(3, base_rating=4.8, prices=[100.0, 100.0, 100.0])
    transactions = _tx([0, 1, 2])
    cfg = _cfg(score_min=1.0, score_max=5.0)
    result = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=cfg)
    ratings = result[COL_RATING_VALUE].to_numpy()
    assert all(1.0 <= r <= 5.0 for r in ratings), f"ratings out of range: {ratings}"


# ---------------------------------------------------------------------------
# 12.5-T2  review_rng_seed_stable — same seed → same rating path
# ---------------------------------------------------------------------------


def test_review_rng_seed_stable() -> None:
    """Identical inputs + same seed must produce bit-identical rating updates."""
    products = _products(3, base_rating=4.0)
    transactions = _tx([0, 1, 2])
    cfg = _cfg()

    result_a = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=cfg)
    result_b = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=cfg)

    assert result_a[COL_RATING_VALUE].to_list() == result_b[COL_RATING_VALUE].to_list(), (
        "same seed must produce identical rating path"
    )


def test_different_seeds_produce_different_ratings() -> None:
    """Different seeds (almost surely) produce different review scores."""
    products = _products(5, base_rating=4.0)
    transactions = _tx([0, 1, 2, 3, 4])
    cfg = _cfg()

    result_42 = update_rating_ema(products, transactions, seed=42, tick_id=0, cfg=cfg)
    result_99 = update_rating_ema(products, transactions, seed=99, tick_id=0, cfg=cfg)

    # Aggregate into scalar to avoid per-element flakiness from floating precision
    diff = sum(
        abs(a - b)
        for a, b in zip(
            result_42[COL_RATING_VALUE].to_list(),
            result_99[COL_RATING_VALUE].to_list(),
        )
    )
    assert diff > 0.0, "different seeds must produce different ratings"


# ---------------------------------------------------------------------------
# 12.5-T3  review_score_price_sensitive — overpriced listing gets lower reviews
# ---------------------------------------------------------------------------


def test_review_score_price_sensitive() -> None:
    """
    Listing priced far above category median receives lower average review score
    than a listing priced at or below the median (ceteris paribus, same seed).
    """
    # 4 listings, 2 categories (2 each):
    # cat 0: listing 0 at cat_median=100, listing 1 at 500 (5× above median)
    # cat 1: listing 2 at cat_median=100, listing 3 at 500
    # cat_median = median of listing prices per category
    products = _products(
        4,
        base_rating=4.0,
        prices=[100.0, 500.0, 100.0, 500.0],
        category_ids=[0, 0, 1, 1],
    )
    # Transactions with matching prices_paid so price_paid/cat_median penalty kicks in
    n_tx = 30
    tx_listings = [0] * n_tx + [1] * n_tx + [2] * n_tx + [3] * n_tx
    tx_prices = [100.0] * n_tx + [500.0] * n_tx + [100.0] * n_tx + [500.0] * n_tx
    transactions = _tx(tx_listings, prices_paid=tx_prices)

    scores = compute_review_scores(transactions, products, seed=_SEED, tick_id=_TICK)

    # Group scores by listing
    scores_by_listing: dict[int, list[float]] = {0: [], 1: [], 2: [], 3: []}
    for i, lid in enumerate(tx_listings):
        scores_by_listing[lid].append(float(scores[i]))

    avg_0 = np.mean(scores_by_listing[0])   # fair price cat 0
    avg_1 = np.mean(scores_by_listing[1])   # overpriced cat 0
    avg_2 = np.mean(scores_by_listing[2])   # fair price cat 1
    avg_3 = np.mean(scores_by_listing[3])   # overpriced cat 1

    assert avg_0 > avg_1, (
        f"fair listing 0 avg={avg_0:.2f} should score higher than overpriced listing 1 avg={avg_1:.2f}"
    )
    assert avg_2 > avg_3, (
        f"fair listing 2 avg={avg_2:.2f} should score higher than overpriced listing 3 avg={avg_3:.2f}"
    )


# ---------------------------------------------------------------------------
# 12.5-T4  disabled_config_noop — DynamicRatingConfig(enabled=False) → no change
# ---------------------------------------------------------------------------


def test_disabled_config_noop() -> None:
    """When DynamicRatingConfig.enabled=False, ratings must be unchanged regardless of transactions."""
    products = _products(3, base_rating=3.5)
    transactions = _tx([0, 1, 2])
    cfg = _cfg(enabled=False)

    result = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=cfg)

    original = products[COL_RATING_VALUE].to_list()
    updated = result[COL_RATING_VALUE].to_list()
    assert updated == original, "disabled rating EMA must be a noop"


# ---------------------------------------------------------------------------
# 12.5-T5  ema_gamma_scales_magnitude — larger γ means faster rating movement
# ---------------------------------------------------------------------------


def test_ema_gamma_scales_magnitude() -> None:
    """Larger γ produces larger rating change in one tick."""
    products = _products(1, base_rating=4.0)
    transactions = _tx([0])

    result_slow = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=_cfg(gamma=0.01))
    result_fast = update_rating_ema(products, transactions, seed=_SEED, tick_id=_TICK, cfg=_cfg(gamma=0.50))

    base = 4.0
    delta_slow = abs(float(result_slow[COL_RATING_VALUE][0]) - base)
    delta_fast = abs(float(result_fast[COL_RATING_VALUE][0]) - base)

    assert delta_fast > delta_slow, (
        f"higher γ must move rating further: slow Δ={delta_slow:.4f}, fast Δ={delta_fast:.4f}"
    )
