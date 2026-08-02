# Назначение файла: Panic severe + p50_tx drop acceptance tests (Slice 12.6, Spec 012 §13.6).
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.analytics.p50_metrics import P50Source, compute_p50_drop, compute_tick_p50
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    PLATFORM_DEFAULTS,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.simulation.repricing import apply_repricing_tick, build_stress_repricing_profile

# ─── helpers ────────────────────────────────────────────────────────────────


def _tx_df(prices_paid: list[float]) -> pl.DataFrame:
    return pl.DataFrame({COL_PRICE_PAID: pl.Series(prices_paid, dtype=pl.Float32)})


def _sellers_near_floor(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxVolume"] * n,
            "capital": [500.0] * n,
            COL_MARGIN_FLOOR: [0.05] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings_near_unit_cost(n: int = 8) -> pl.DataFrame:
    """Listings where price is just slightly above unit_cost — worst-case for unit_cost guard."""
    unit_costs = np.linspace(50.0, 200.0, n).astype(np.float32)
    # 2% above unit_cost = minimal viable headroom before panic repricing kicks in
    prices = (unit_costs * 1.02).astype(np.float32)
    return pl.DataFrame(
        {
            COL_LISTING_ID: pl.Series(list(range(n)), dtype=pl.Int32),
            COL_SELLER_ID: pl.Series(list(range(n)), dtype=pl.Int32),
            COL_UNIT_COST: pl.Series(unit_costs, dtype=pl.Float32),
            COL_PRICE: pl.Series(prices, dtype=pl.Float32),
            COL_DEMAND_INDEX: pl.Series([0.5] * n, dtype=pl.Float32),
            COL_CATEGORY_ID: pl.Series([0] * n, dtype=pl.Int32),
            **{k: pl.Series([v] * n, dtype=pl.Float32) for k, v in PLATFORM_DEFAULTS.items()},
        }
    )


# ─── T4: sparse-tx fallback (unit tests, fast) ───────────────────────────────


def test_sparse_tx_falls_back_to_listing_p50() -> None:
    """When n_tx < n_tx_min, listing_p50 is returned and source = listing_fallback."""
    sparse_tx = _tx_df([80.0, 85.0])  # 2 < n_tx_min=5
    val, src = compute_tick_p50(sparse_tx, n_tx_min=5, listing_p50=100.0)
    assert src == "listing_fallback"
    assert val == pytest.approx(100.0)


def test_dense_tx_uses_transaction_p50() -> None:
    """When n_tx >= n_tx_min, transaction median is returned and source = transaction."""
    prices = [80.0, 82.0, 85.0, 90.0, 95.0, 100.0]  # 6 >= n_tx_min=5
    dense_tx = _tx_df(prices)
    val, src = compute_tick_p50(dense_tx, n_tx_min=5, listing_p50=200.0)
    assert src == "transaction"
    assert val == pytest.approx(float(np.median(prices)), rel=1e-4)


def test_empty_tx_falls_back_to_listing_p50() -> None:
    """Empty transactions always fall back to listing_p50."""
    empty_tx = pl.DataFrame({COL_PRICE_PAID: pl.Series([], dtype=pl.Float32)})
    val, src = compute_tick_p50(empty_tx, n_tx_min=5, listing_p50=77.0)
    assert src == "listing_fallback"
    assert val == pytest.approx(77.0)


def test_compute_p50_drop_mixed_source_flagged() -> None:
    """If pre-window uses transactions but trough-window is sparse, source = mixed."""
    dense = _tx_df([100.0] * 10)
    sparse = _tx_df([50.0])  # 1 tx → fallback

    tx_by_tick = [dense] * 20 + [sparse] * 10
    listing_p50_by_tick = [100.0] * 20 + [80.0] * 10  # listing fallback = 80

    drop, src = compute_p50_drop(
        tx_by_tick,
        listing_p50_by_tick,
        shock_tick=20,
        w_pre=20,
        w_post=10,
        n_tx_min=5,
    )
    assert src == "mixed"
    # pre_mean ≈ 100.0, trough = 80.0 (from listing fallback) → drop = 0.20
    assert drop == pytest.approx(0.20, rel=0.05)


# ─── T2: panic never below unit_cost (focused repricing unit test) ────────────


def test_panic_never_below_unit_cost() -> None:
    """
    Under severe panic stress repricing, price must never fall below unit_cost.
    Spec 011 unit_cost guard is non-negotiable even with panic_step_gain × 4.
    Spec 012 §5.1: forbid_price_below_unit_cost — не отключать.
    """
    n = 12
    sellers = _sellers_near_floor(n)
    listings = _listings_near_unit_cost(n)
    config = RepricingConfig.market_with_headroom()

    macro = MacroState(
        stress=0.95,  # well above panic_stress_threshold=0.40
        regime=MacroRegime.STRESS,
        peak_stress=0.95,
    )
    profile = build_stress_repricing_profile(macro, config)
    assert profile is not None and profile.panic_mode, "Expected panic_mode at stress=0.95"

    result = apply_repricing_tick(sellers, listings, tick=1, config=config, repricing_profile=profile)
    prices = result[COL_PRICE].to_numpy()
    unit_costs = result[COL_UNIT_COST].to_numpy()

    assert np.all(prices >= unit_costs * 0.9999), (
        f"Panic violated unit_cost guard: min(price/unit_cost) = {(prices / unit_costs).min():.6f}"
    )


# ─── T1, T3: severe integration tests (slow) ─────────────────────────────────


@pytest.mark.slow
def test_severe_p50_tx_drop_at_least_15pct() -> None:
    """
    Severe scenario: transaction p50 trough drops ≥ 15% vs pre-shock mean.
    Uses sparse-tx listing fallback for ticks where n_tx < n_tx_min = 5.
    Requires peak_stress > panic_stress_threshold (0.40) — seed=17 reliably produces ~0.45.
    Spec 012 §5.2 acceptance: 12.6-T1.
    """
    from tests.simulation.test_recession_integration import run_severe_recession

    # seed=17 produces peak_stress ≈ 0.45 (above panic threshold 0.40) → 15%+ tx drop
    result = run_severe_recession(seed=17)
    drop, src = compute_p50_drop(
        list(result.transactions_by_tick),
        list(result.price_p50_by_tick),
        shock_tick=result.shock_tick,
        w_pre=20,
        w_post=40,
        n_tx_min=5,
    )
    assert drop >= 0.15, (
        f"p50_tx drop = {drop:.3%} < 15% (source={src}); "
        f"shock_tick={result.shock_tick}, peak_stress={result.peak_stress:.3f}"
    )


@pytest.mark.slow
def test_deterministic_severe_path() -> None:
    """
    Same seed → identical p50 drop value and source label.
    Spec 012 §10 determinism invariant: 12.6-T3.
    """
    from tests.simulation.test_recession_integration import run_severe_recession

    run_a = run_severe_recession(seed=77)
    run_b = run_severe_recession(seed=77)

    drop_a, src_a = compute_p50_drop(
        list(run_a.transactions_by_tick),
        list(run_a.price_p50_by_tick),
        shock_tick=run_a.shock_tick,
    )
    drop_b, src_b = compute_p50_drop(
        list(run_b.transactions_by_tick),
        list(run_b.price_p50_by_tick),
        shock_tick=run_b.shock_tick,
    )

    assert drop_a == pytest.approx(drop_b, rel=1e-6)
    assert src_a == src_b
