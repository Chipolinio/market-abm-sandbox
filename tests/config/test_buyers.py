# Тесты Pydantic-конфига покупателей: DistributionSpec, CategoricalSpec, BuyerPopulationConfig.

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from market_abm.config.buyers import (
    BuyerPopulationConfig,
    CategoricalSpec,
    DistributionSpec,
)
from market_abm.domain.constants import DEVICE_TYPES, PVD_SEGMENTS


# --- DistributionSpec ---


def test_distribution_spec_accepts_valid_lognorm() -> None:
    spec = DistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(3.0)})
    assert spec.family == "lognorm"


def test_distribution_spec_rejects_unknown_family() -> None:
    with pytest.raises(ValidationError):
        DistributionSpec(family="poisson", params={"mu": 1.0})  # type: ignore[arg-type]


def test_distribution_spec_rejects_invalid_scipy_params() -> None:
    with pytest.raises(ValidationError):
        DistributionSpec(family="lognorm", params={"not_a_scipy_param": 1.0})


@pytest.mark.parametrize(
    "family,params",
    [
        ("norm", {"loc": 0.0, "scale": 1.0}),
        ("truncnorm", {"a": 0.0, "b": float("inf"), "loc": -2.0, "scale": 0.5}),
        ("gamma", {"a": 2.0, "scale": 1.0}),
        ("uniform", {"loc": 0.0, "scale": 1.0}),
    ],
)
def test_distribution_spec_accepts_all_supported_families(
    family: str, params: dict[str, float]
) -> None:
    spec = DistributionSpec(family=family, params=params)  # type: ignore[arg-type]
    assert spec.family == family


# --- CategoricalSpec ---


def test_categorical_spec_requires_matching_lengths() -> None:
    with pytest.raises(ValidationError):
        CategoricalSpec(levels=("a", "b"), probabilities=(0.5,))


def test_categorical_spec_requires_probabilities_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        CategoricalSpec(levels=("a", "b"), probabilities=(0.6, 0.6))


def test_categorical_spec_accepts_valid_distribution() -> None:
    spec = CategoricalSpec(levels=("ios", "android"), probabilities=(0.4, 0.6))
    assert sum(spec.probabilities) == pytest.approx(1.0)


# --- BuyerPopulationConfig.default_market ---


def test_default_market_builds_without_error() -> None:
    config = BuyerPopulationConfig.default_market()
    assert isinstance(config, BuyerPopulationConfig)


def test_default_market_uses_domain_device_and_pvd_levels() -> None:
    config = BuyerPopulationConfig.default_market()
    assert config.device_type.levels == DEVICE_TYPES
    assert config.pvd_segment.levels == PVD_SEGMENTS


def test_default_market_distribution_presets_match_spec() -> None:
    config = BuyerPopulationConfig.default_market()

    assert config.budget.family == "lognorm"
    assert config.budget.params["s"] == pytest.approx(0.5)

    assert config.beta_price.family == "truncnorm"
    assert config.beta_price.params["loc"] == pytest.approx(-2.0)

    assert config.beta_delivery.family == "truncnorm"
    assert config.beta_delivery.params["loc"] == pytest.approx(-0.3)

    assert config.beta_rating.family == "truncnorm"
    assert config.beta_rating.params["loc"] == pytest.approx(-0.5)

    assert config.purchase_frequency.family == "uniform"
    assert config.purchase_frequency.params["loc"] == pytest.approx(0.0)
    assert config.purchase_frequency.params["scale"] == pytest.approx(1.0)


def test_default_market_categorical_probabilities_sum_to_one() -> None:
    config = BuyerPopulationConfig.default_market()
    assert sum(config.device_type.probabilities) == pytest.approx(1.0)
    assert sum(config.pvd_segment.probabilities) == pytest.approx(1.0)


def test_default_market_enforce_negative_coefficients_true() -> None:
    config = BuyerPopulationConfig.default_market()
    assert config.enforce_negative_coefficients is True


def test_default_market_ios_multiplier() -> None:
    config = BuyerPopulationConfig.default_market()
    assert config.ios_price_beta_multiplier == pytest.approx(0.85)


def test_default_market_activity_hour_mode() -> None:
    config = BuyerPopulationConfig.default_market()
    assert config.activity_hour == "uniform_discrete"


def test_default_market_impulsive_probability() -> None:
    config = BuyerPopulationConfig.default_market()
    assert config.impulsive_probability == pytest.approx(0.15)


def test_buyer_population_config_rejects_non_positive_n_buyers() -> None:
    with pytest.raises(ValidationError):
        BuyerPopulationConfig.default_market(n_buyers=0)


def test_buyer_population_config_device_levels_must_be_subset_of_domain() -> None:
    base = BuyerPopulationConfig.default_market()
    with pytest.raises(ValidationError):
        BuyerPopulationConfig(
            **{
                **base.model_dump(),
                "device_type": CategoricalSpec(
                    levels=("ios", "unknown_device"),
                    probabilities=(0.5, 0.5),
                ),
            }
        )


def test_buyer_population_config_pvd_levels_must_be_subset_of_domain() -> None:
    base = BuyerPopulationConfig.default_market()
    with pytest.raises(ValidationError):
        BuyerPopulationConfig(
            **{
                **base.model_dump(),
                "pvd_segment": CategoricalSpec(
                    levels=("rich", "vip"),
                    probabilities=(0.5, 0.5),
                ),
            }
        )


def test_buyer_population_config_custom_n_buyers_and_seed() -> None:
    config = BuyerPopulationConfig.default_market(n_buyers=500, seed=7)
    assert config.n_buyers == 500
    assert config.seed == 7
