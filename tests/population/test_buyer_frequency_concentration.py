# Spec 012, Slice 12.1: lognorm purchase_frequency + GMV concentration tests.
# RED before: default_market() uses uniform — top-20% share ~36%, no freq_eps clip.
# GREEN after: lognorm(s=0.8, scale=0.25) + clip(0.02, 1.0).

from __future__ import annotations

import math

import numpy as np
import pytest

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.common import DistributionSpec
from market_abm.domain.constants import COL_FREQ_BASELINE
from market_abm.population.buyers import generate_buyers

_N_BUYERS: int = 10_000
_SEED: int = 42
_FREQ_EPS: float = 0.02  # lower clip bound per §16.1

# freq values are stored as float32; float32(0.02) rounds to 0.019999999... in float64.
# Use the f32 representation as the comparison floor to avoid false failures.
_FREQ_EPS_F32: float = float(np.float32(_FREQ_EPS))

# Top-20% GMV share acceptance band (§13.1 / §3.1)
_SHARE_LO: float = 0.70
_SHARE_HI: float = 0.85


@pytest.fixture
def lognorm_config() -> BuyerPopulationConfig:
    """Default market preset — должен использовать lognorm после 12.1 GREEN."""
    return BuyerPopulationConfig.default_market(n_buyers=_N_BUYERS, seed=_SEED)


@pytest.fixture
def uniform_config() -> BuyerPopulationConfig:
    """Явный uniform — backward compat / legacy opt-in (T3)."""
    return BuyerPopulationConfig.default_market(
        n_buyers=_N_BUYERS,
        seed=_SEED,
    ).model_copy(
        update={
            "purchase_frequency": DistributionSpec(
                family="uniform",
                params={"loc": 0.0, "scale": 1.0},
            )
        }
    )


# ---------------------------------------------------------------------------
# 12.1-T1  GMV concentration: top-20% buyers ∈ [0.70, 0.85]
# ---------------------------------------------------------------------------


def test_top20_buyers_gmv_share_in_band(lognorm_config: BuyerPopulationConfig) -> None:
    """Top-20% buyers by freq_baseline account for 70–85% of baseline GMV proxy."""
    df = generate_buyers(lognorm_config)
    freq = df[COL_FREQ_BASELINE].to_numpy(allow_copy=False)

    threshold = np.percentile(freq, 80.0)
    top20_mask = freq >= threshold
    total = float(freq.sum())
    assert total > 0.0, "freq_baseline sum must be positive"

    share = float(freq[top20_mask].sum()) / total
    assert _SHARE_LO <= share <= _SHARE_HI, (
        f"top-20% GMV share={share:.4f} not in [{_SHARE_LO}, {_SHARE_HI}]; "
        f"expected lognorm distribution in default_market()"
    )


# ---------------------------------------------------------------------------
# 12.1-T2  Clip invariant: all freq_baseline ∈ (freq_eps, 1.0]
# ---------------------------------------------------------------------------


def test_freq_clipped_to_unit_interval(lognorm_config: BuyerPopulationConfig) -> None:
    """All freq_baseline values must lie in (freq_eps, 1.0] after clip."""
    df = generate_buyers(lognorm_config)
    freq = df[COL_FREQ_BASELINE].to_numpy(allow_copy=False)

    freq_min = float(freq.min())
    freq_max = float(freq.max())

    assert freq_min >= _FREQ_EPS_F32, (
        f"freq_baseline min={freq_min:.8f} < freq_eps(f32)={_FREQ_EPS_F32:.8f}; "
        f"population/buyers.py must clip to ({_FREQ_EPS}, 1.0]"
    )
    assert freq_max <= 1.0, (
        f"freq_baseline max={freq_max:.6f} > 1.0; "
        f"upper clip to 1.0 not applied"
    )
    assert np.all(freq > 0.0), "freq_baseline must be strictly positive (no zero values)"


# ---------------------------------------------------------------------------
# 12.1-T3  Legacy opt-in: explicit uniform config still accepted and works
# ---------------------------------------------------------------------------


def test_legacy_uniform_opt_in(uniform_config: BuyerPopulationConfig) -> None:
    """Explicit uniform DistributionSpec is still valid; backward compat guard."""
    assert uniform_config.purchase_frequency.family == "uniform"

    df = generate_buyers(uniform_config)
    assert df.height == _N_BUYERS

    freq = df[COL_FREQ_BASELINE].to_numpy(allow_copy=False)

    # uniform remains in [0, 1]
    assert float(freq.min()) >= 0.0
    assert float(freq.max()) <= 1.0

    # uniform does NOT produce heavy-buyer concentration — regression guard
    threshold = np.percentile(freq, 80.0)
    share = float(freq[freq >= threshold].sum()) / float(freq.sum())
    assert share < _SHARE_LO, (
        f"uniform config produced top-20% share={share:.4f} >= {_SHARE_LO}; "
        f"something is unexpectedly concentrating the uniform distribution"
    )
