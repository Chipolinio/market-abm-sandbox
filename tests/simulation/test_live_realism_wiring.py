# Spec 013, Slice 13.1: live wire ranking + consideration into step hot path.
# RED before: step does not call compute_ranking_scores / does not pass arrays to choice.
# GREEN after: one ranking precompute/tick → category_ids + ranking_scores in choice;
#              products_next carries ranking_score (extra col preserved).

from __future__ import annotations

from dataclasses import replace

import numpy as np
import polars as pl
import pytest

from market_abm.config.ranking import RankingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import (
    ChoiceModelConfig,
    ReferencePriceConfig,
    SimulationStepConfig,
)
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
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RANKING_SCORE,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.choice import choose_listings_for_all_buyers
from market_abm.simulation.context import default_simulation_context
from market_abm.simulation.ranking import compute_ranking_scores
from market_abm.simulation.ref_price import (
    advance_realism_windows,
    resolve_reference_price,
)
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

    products_next, _tx, _sellers_state, _ = step(buyers, sellers, products, cfg)

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
    ref_price = resolve_reference_price(None, ranked, choice_cfg.reference_price)

    wired = choose_listings_for_all_buyers(
        buyers,
        ranked,
        seed=_SEED,
        config=choice_cfg,
        ref_price=ref_price,
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

    _products_next, tx, _sellers_state, _ = step(buyers, sellers, products, cfg)
    live_ids = _purchase_listing_ids(tx)

    assert live_ids, "live step must produce purchases"
    assert live_ids != legacy_ids, (
        "live step must not follow legacy rng.choice path (ranking arrays required)"
    )
    assert live_ids == wired_ids, (
        "live step choice multiset must match explicit wired ranking path (same seed)"
    )


# ---------------------------------------------------------------------------
# 13.2 helpers — dual-price market for reference-price penalty
# ---------------------------------------------------------------------------


def _ref_pair_products() -> pl.DataFrame:
    """Two same-cat listings: at-ref (100) vs far above hist (300); equal ratings."""
    return pl.DataFrame(
        {
            COL_LISTING_ID: [0, 1],
            COL_SELLER_ID: [0, 1],
            COL_UNIT_COST: [20.0, 20.0],
            COL_PRICE: [100.0, 300.0],
            COL_DEMAND_INDEX: [1.0, 1.0],
            COL_DELIVERY_DAYS: [3.0, 3.0],
            COL_RATING_VALUE: [4.0, 4.0],
            COL_CATEGORY_ID: [0, 0],
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


def _count_listing(tx: pl.DataFrame, listing_id: int) -> int:
    if tx.height == 0:
        return 0
    return int((tx[COL_LISTING_ID] == listing_id).sum())


# ---------------------------------------------------------------------------
# 13.2-T1  live_ref_price_penalizes_above_hist
# ---------------------------------------------------------------------------


def test_live_ref_price_penalizes_above_hist() -> None:
    """
    Filled tx_p50_window: expensive listing gets fewer purchases when ref enabled
    vs disabled (Spec 013 §13.2-T1).
    """
    # Neutral price beta so MNL does not already wipe the expensive listing;
    # reference penalty is the only asymmetric utility term.
    buyers = pl.DataFrame(
        {
            COL_BUYER_ID: list(range(150)),
            COL_BUDGET: [500.0] * 150,
            COL_BETA_PRICE: [0.0] * 150,
            COL_BETA_DELIVERY: [0.0] * 150,
            COL_BETA_RATING: [0.0] * 150,
            "device_type": ["android"] * 150,
            "pvd_segment": ["standard"] * 150,
            "activity_hour": [12] * 150,
            "is_impulsive": [False] * 150,
            COL_PURCHASE_FREQUENCY: [1.0] * 150,
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
    products = _ref_pair_products()
    sellers = _sellers_df(products.height)
    ctx = replace(
        default_simulation_context(tick_id=_TICK),
        tx_p50_window=(100.0,) * 5,
    )

    ranking = RankingConfig(
        w1=0.40, w2=0.35, w3=0.25, top_k=2, organic_m=0, n_categories=1
    )
    cfg_on = _step_cfg(
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=20,
            outside_utility_bias=-100.0,
            ranking=ranking,
            reference_price=ReferencePriceConfig(enabled=True, beta_ref=4.0),
        )
    )
    cfg_off = _step_cfg(
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=20,
            outside_utility_bias=-100.0,
            ranking=ranking,
            reference_price=ReferencePriceConfig(enabled=False),
        )
    )

    _p_on, tx_on, _s_on, ctx_on = step(
        buyers, sellers, products, cfg_on, simulation_context=ctx
    )
    _p_off, tx_off, _s_off, _ctx_off = step(
        buyers, sellers, products, cfg_off, simulation_context=ctx
    )

    expensive_on = _count_listing(tx_on, 1)
    expensive_off = _count_listing(tx_off, 1)
    assert tx_on.height > 0 and tx_off.height > 0
    assert expensive_off > 0, "disabled path must still buy expensive sometimes"
    assert expensive_on < expensive_off, (
        f"ref penalty must reduce expensive listing share: "
        f"enabled={expensive_on} disabled={expensive_off}"
    )
    # Window advanced on returned ctx (pure replace)
    assert ctx_on is not None
    assert len(ctx_on.tx_p50_window) == len(ctx.tx_p50_window) + 1
    assert ctx.tx_p50_window == (100.0,) * 5  # input ctx not mutated


# ---------------------------------------------------------------------------
# 13.2-T2  live_ref_disabled_noop
# ---------------------------------------------------------------------------


def test_live_ref_disabled_noop() -> None:
    """
    enabled=False → live step matches choose(..., ref_price=None) at same seed
    even with a filled hist window (Spec 013 §13.2-T2).
    """
    buyers = _buyers_df()
    products = _ref_pair_products()
    sellers = _sellers_df(products.height)
    ctx = replace(
        default_simulation_context(tick_id=_TICK),
        tx_p50_window=(100.0,) * 8,
    )
    choice_cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=20,
        outside_utility_bias=-100.0,
        ranking=RankingConfig(
            w1=0.40, w2=0.35, w3=0.25, top_k=2, organic_m=0, n_categories=1
        ),
        reference_price=ReferencePriceConfig(enabled=False),
    )
    cfg = _step_cfg(choice=choice_cfg)

    ranked, category_ids, ranking_scores = _choice_arrays(products, choice_cfg)
    assert resolve_reference_price(ctx, ranked, choice_cfg.reference_price) is None

    baseline = choose_listings_for_all_buyers(
        buyers,
        ranked,
        seed=_SEED,
        config=choice_cfg,
        ref_price=None,
        category_ids=category_ids,
        ranking_scores=ranking_scores,
    )
    _products_next, tx, _sellers_state, _ctx_next = step(
        buyers, sellers, products, cfg, simulation_context=ctx
    )
    assert _purchase_listing_ids(tx) == _purchase_listing_ids(baseline)


# ---------------------------------------------------------------------------
# 13.2 unit: resolve / advance helpers
# ---------------------------------------------------------------------------


def test_resolve_reference_price_cold_start_and_window() -> None:
    products = _ref_pair_products()
    cfg = ReferencePriceConfig(enabled=True, beta_ref=1.0, window_ticks=20)
    cold = resolve_reference_price(None, products, cfg)
    assert cold == pytest.approx(200.0)  # median(100, 300)

    ctx = replace(
        default_simulation_context(tick_id=0),
        tx_p50_window=(80.0, 100.0, 120.0),
    )
    assert resolve_reference_price(ctx, products, cfg) == pytest.approx(100.0)
    assert resolve_reference_price(
        ctx, products, ReferencePriceConfig(enabled=False)
    ) is None


def test_advance_realism_windows_appends_and_is_pure() -> None:
    products = _ref_pair_products()
    ctx = default_simulation_context(tick_id=0)
    tx = pl.DataFrame(
        {
            "tick_id": [0] * 6,
            COL_BUYER_ID: list(range(6)),
            COL_LISTING_ID: [0, 0, 0, 1, 1, 1],
            COL_SELLER_ID: [0, 0, 0, 1, 1, 1],
            COL_PRICE_PAID: [100.0] * 3 + [300.0] * 3,
            COL_UNIT_COST: [20.0] * 6,
            "gross_margin": [80.0] * 3 + [280.0] * 3,
        }
    ).with_columns(
        pl.col("tick_id").cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col("gross_margin").cast(pl.Float32),
    )
    cfg = ReferencePriceConfig(enabled=True, window_ticks=20)
    nxt = advance_realism_windows(ctx, tx, products, ref_cfg=cfg)
    assert ctx.tx_p50_window == ()
    assert len(nxt.tx_p50_window) == 1
    assert nxt.tx_p50_window[0] == pytest.approx(200.0)  # median price_paid
    assert len(nxt.sales_counts_ring) == 1
    assert dict(nxt.sales_counts_ring[0]) == {0: 3, 1: 3}


# ---------------------------------------------------------------------------
# 13.3-T2  live_wiring_seed_stable
# ---------------------------------------------------------------------------


def test_live_wiring_seed_stable() -> None:
    """
    Two short live step loops with the same seed must produce identical GMV
    and purchase listing sequences (Spec 013 §13.3-T2 / §10).
    """
    n_ticks = 5

    def _gmv_and_listings(seed: int) -> tuple[list[float], list[list[int]]]:
        buyers = _buyers_df(40)
        products = _asymmetric_products()
        sellers = _sellers_df(products.height)
        ctx = default_simulation_context(tick_id=0)
        gmvs: list[float] = []
        listing_series: list[list[int]] = []
        for tick_id in range(n_ticks):
            cfg = _step_cfg(tick_id=tick_id, seed=seed)
            products, tx, _sellers_state, ctx_next = step(
                buyers,
                sellers,
                products,
                cfg,
                simulation_context=replace(ctx, tick_id=tick_id),
            )
            if ctx_next is not None:
                ctx = ctx_next
            gmv = float(tx[COL_PRICE_PAID].sum()) if tx.height > 0 else 0.0
            gmvs.append(gmv)
            listing_series.append(_purchase_listing_ids(tx))
        return gmvs, listing_series

    gmv_a, listings_a = _gmv_and_listings(_SEED)
    gmv_b, listings_b = _gmv_and_listings(_SEED)
    assert gmv_a == gmv_b
    assert listings_a == listings_b
    assert any(g > 0.0 for g in gmv_a), "fixture must produce non-zero GMV"
