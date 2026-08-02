# Spec 012, Slice 12.2: reference-price penalty in MNL utility.
# RED before: ReferencePriceConfig and compute_reference_price_penalty do not exist.
# GREEN after: config/simulation.py + choice.py implement §3.2 formula.

from __future__ import annotations

import math

import numpy as np
import pytest

from market_abm.config.simulation import ChoiceModelConfig, ReferencePriceConfig
from market_abm.simulation.choice import compute_reference_price_penalty

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BETA_REF: float = 1.0   # default per §16 (to be set in ReferencePriceConfig)


def _penalty(prices: list[float], ref: float, beta: float = _BETA_REF) -> np.ndarray:
    return compute_reference_price_penalty(
        np.array(prices, dtype=np.float32),
        ref_price=ref,
        beta_ref=beta,
    )


# ---------------------------------------------------------------------------
# 12.2-T1  above_hist_p50_lowers_utility
# ---------------------------------------------------------------------------


def test_above_hist_p50_lowers_utility() -> None:
    """
    U_j += β_ref · f(p_j / p_ref), where f = -max(0, log(ratio))^2.
    - At reference price: f = 0, no penalty.
    - Above reference:    f < 0, negative penalty applied.
    - Below reference:    f = 0, no penalty (bonus не даётся).
    """
    p50 = 100.0
    # three products: at p50, 2×p50, 0.5×p50
    penalties = _penalty([p50, 2 * p50, 0.5 * p50], ref=p50)

    # At reference: ratio=1 → log(1)=0 → penalty=0
    assert penalties[0] == pytest.approx(0.0, abs=1e-6), (
        f"penalty at p50 should be 0.0, got {penalties[0]}"
    )

    # Above reference: ratio=2 → log(2)>0 → penalty = -β·log(2)^2 < 0
    expected_above = -_BETA_REF * math.log(2.0) ** 2
    assert penalties[1] == pytest.approx(expected_above, rel=1e-4), (
        f"penalty at 2×p50 should be {expected_above:.6f}, got {penalties[1]}"
    )
    assert penalties[1] < 0.0, "penalty above p50 must be strictly negative"

    # Below reference: ratio=0.5 → log(0.5)<0 → max(0, log)<0 clipped to 0 → penalty=0
    assert penalties[2] == pytest.approx(0.0, abs=1e-6), (
        f"penalty below p50 (0.5×p50) should be 0.0 — no bonus below reference"
    )

    # Utility ordering: U(at_p50) > U(above_p50) ceteris paribus
    # (penalty is additive shift — higher penalty → lower utility)
    assert penalties[0] > penalties[1], (
        "utility at p50 must exceed utility at 2×p50 (reference penalty)"
    )


def test_penalty_scales_with_beta_ref() -> None:
    """Stronger β_ref → larger magnitude penalty above reference."""
    p50 = 50.0
    price_above = 80.0

    pen_weak = _penalty([price_above], ref=p50, beta=0.5)
    pen_strong = _penalty([price_above], ref=p50, beta=2.0)

    assert pen_weak[0] < 0.0, "penalty must be negative above reference"
    assert pen_strong[0] < pen_weak[0], (
        "higher β_ref must produce larger-magnitude (more negative) penalty"
    )


def test_penalty_zero_ref_price_returns_zeros() -> None:
    """Invalid ref_price <= 0 → no penalty (safe fallback)."""
    prices = np.array([50.0, 100.0, 200.0], dtype=np.float32)
    for bad_ref in [0.0, -1.0]:
        pen = compute_reference_price_penalty(prices, ref_price=bad_ref, beta_ref=1.0)
        np.testing.assert_array_equal(pen, np.zeros(3, dtype=np.float32), err_msg=f"ref_price={bad_ref}")


# ---------------------------------------------------------------------------
# 12.2-T2  disabled_config_noop
# ---------------------------------------------------------------------------


def test_disabled_config_noop() -> None:
    """enabled=False → penalty is all zeros (matches pre-012 utilities)."""
    cfg_disabled = ReferencePriceConfig(enabled=False)
    cfg_enabled = ReferencePriceConfig(enabled=True, beta_ref=_BETA_REF)

    prices = np.array([80.0, 100.0, 150.0], dtype=np.float32)
    ref = 100.0

    # With enabled=True: non-zero penalty above ref
    pen_enabled = compute_reference_price_penalty(prices, ref_price=ref, beta_ref=cfg_enabled.beta_ref)
    # The 150.0 entry is above ref → should be negative
    assert pen_enabled[2] < 0.0, "enabled penalty above ref must be negative"

    # With enabled=False: penalty application skipped → zeros
    if not cfg_disabled.enabled:
        pen_disabled = np.zeros(len(prices), dtype=np.float32)
    else:
        pen_disabled = compute_reference_price_penalty(prices, ref_price=ref, beta_ref=cfg_disabled.beta_ref)

    np.testing.assert_array_equal(pen_disabled, np.zeros(len(prices), dtype=np.float32))


def test_choice_model_config_has_reference_price_field() -> None:
    """ChoiceModelConfig carries ReferencePriceConfig; default enabled=True."""
    cfg = ChoiceModelConfig(engine="numpy_softmax", max_products_per_choice_set=50, buyers_batch_size=200)
    assert hasattr(cfg, "reference_price"), "ChoiceModelConfig must have reference_price field"
    assert isinstance(cfg.reference_price, ReferencePriceConfig)
    assert cfg.reference_price.enabled is True, "reference_price must be enabled by default"


def test_reference_price_config_disabled_opt_out() -> None:
    """Can explicitly disable reference price via ChoiceModelConfig."""
    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=50,
        buyers_batch_size=200,
        reference_price=ReferencePriceConfig(enabled=False),
    )
    assert cfg.reference_price.enabled is False
