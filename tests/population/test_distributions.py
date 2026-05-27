from __future__ import annotations

import math

import numpy as np
import pytest

from market_abm.config.buyers import BuyerPopulationConfig, CategoricalSpec, DistributionSpec
from market_abm.population.distributions import (
    sample_activity_hours,
    sample_bernoulli,
    sample_categorical,
    sample_from_spec,
)


# --- sample_from_spec: lognorm ---


def test_sample_from_spec_lognorm_returns_length_n_buyers() -> None:
    spec = DistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(3.0)})
    rng = np.random.default_rng(0)
    out = sample_from_spec(spec, size=10_000, rng=rng)
    assert out.shape == (10_000,)
    assert out.dtype == np.float64


def test_sample_from_spec_lognorm_is_reproducible_with_same_rng() -> None:
    spec = DistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(3.0)})
    rng_a = np.random.default_rng(99)
    rng_b = np.random.default_rng(99)
    a = sample_from_spec(spec, size=500, rng=rng_a)
    b = sample_from_spec(spec, size=500, rng=rng_b)
    np.testing.assert_array_equal(a, b)


def test_sample_from_spec_lognorm_samples_are_strictly_positive() -> None:
    spec = DistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(3.0)})
    out = sample_from_spec(spec, size=5_000, rng=np.random.default_rng(1))
    assert np.all(out > 0)


# --- sample_from_spec: truncnorm ---


def test_sample_from_spec_truncnorm_returns_length_n_buyers() -> None:
    spec = DistributionSpec(
        family="truncnorm",
        params={"a": 0.0, "b": float("inf"), "loc": -2.0, "scale": 0.5},
    )
    out = sample_from_spec(spec, size=8_000, rng=np.random.default_rng(2))
    assert out.shape == (8_000,)


def test_sample_from_spec_truncnorm_default_beta_price_all_negative() -> None:
    """Пресет beta_price: truncnorm с a=0 → сэмплы < 0 (коэффициенты утилиты)."""
    spec = BuyerPopulationConfig.default_market().beta_price
    out = sample_from_spec(spec, size=3_000, rng=np.random.default_rng(3))
    assert np.all(out < 0)


def test_sample_from_spec_truncnorm_reproducible() -> None:
    spec = DistributionSpec(
        family="truncnorm",
        params={"a": 0.0, "b": float("inf"), "loc": -0.3, "scale": 0.1},
    )
    a = sample_from_spec(spec, size=200, rng=np.random.default_rng(7))
    b = sample_from_spec(spec, size=200, rng=np.random.default_rng(7))
    np.testing.assert_array_equal(a, b)


def test_sample_from_spec_rejects_non_positive_size() -> None:
    spec = DistributionSpec(family="norm", params={"loc": 0.0, "scale": 1.0})
    with pytest.raises(ValueError, match="size"):
        sample_from_spec(spec, size=0, rng=np.random.default_rng(0))


@pytest.mark.parametrize(
    "family,params",
    [
        ("norm", {"loc": 1.0, "scale": 0.2}),
        ("gamma", {"a": 2.0, "scale": 1.0}),
        ("uniform", {"loc": 0.0, "scale": 1.0}),
    ],
)
def test_sample_from_spec_other_families_shape(family: str, params: dict[str, float]) -> None:
    spec = DistributionSpec(family=family, params=params)  # type: ignore[arg-type]
    out = sample_from_spec(spec, size=100, rng=np.random.default_rng(4))
    assert out.shape == (100,)


# --- categorical / bernoulli / activity hours ---


def test_sample_categorical_respects_levels_and_length() -> None:
    spec = CategoricalSpec(levels=("ios", "android", "desktop"), probabilities=(0.25, 0.45, 0.30))
    out = sample_categorical(spec, size=2_000, rng=np.random.default_rng(5))
    assert out.shape == (2_000,)
    assert set(out.tolist()).issubset({"ios", "android", "desktop"})


def test_sample_bernoulli_returns_bool_length() -> None:
    out = sample_bernoulli(0.15, size=1_000, rng=np.random.default_rng(6))
    assert out.shape == (1_000,)
    assert out.dtype == bool


def test_sample_activity_hours_in_0_23() -> None:
    out = sample_activity_hours(size=500, rng=np.random.default_rng(8))
    assert out.shape == (500,)
    assert out.dtype == np.uint8
    assert out.min() >= 0
    assert out.max() <= 23
