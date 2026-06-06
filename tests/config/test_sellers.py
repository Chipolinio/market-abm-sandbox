# Purpose: Validate SellerPopulationConfig contracts and default market preset.
# Core idea: Keep config layer deterministic and domain-aligned via strict Pydantic checks.
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from market_abm.config.buyers import CategoricalSpec, DistributionSpec
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.domain.constants import STRATEGY_TYPES


def test_default_market_builds_without_error() -> None:
    config = SellerPopulationConfig.default_market()
    assert isinstance(config, SellerPopulationConfig)


def test_default_market_uses_domain_strategy_levels() -> None:
    config = SellerPopulationConfig.default_market()
    assert config.strategy_type.levels == STRATEGY_TYPES


def test_default_market_distribution_presets_match_spec() -> None:
    config = SellerPopulationConfig.default_market()

    assert config.capital.family == "lognorm"
    assert config.capital.params["s"] == pytest.approx(0.4)
    assert config.capital.params["scale"] == pytest.approx(math.exp(2.5))

    assert config.margin_floor.family == "uniform"
    assert config.margin_floor.params["loc"] == pytest.approx(0.15)
    assert config.margin_floor.params["scale"] == pytest.approx(0.20)

    assert config.repricing_speed.family == "uniform"
    assert config.repricing_speed.params["loc"] == pytest.approx(1.0)
    assert config.repricing_speed.params["scale"] == pytest.approx(5.0)


def test_default_market_strategy_probabilities_sum_to_one() -> None:
    config = SellerPopulationConfig.default_market()
    assert sum(config.strategy_type.probabilities) == pytest.approx(1.0)


def test_seller_population_config_rejects_non_positive_n_sellers() -> None:
    with pytest.raises(ValidationError):
        SellerPopulationConfig.default_market(n_sellers=0)


def test_seller_population_config_rejects_unknown_strategy_level() -> None:
    base = SellerPopulationConfig.default_market()
    with pytest.raises(ValidationError):
        SellerPopulationConfig(
            **{
                **base.model_dump(),
                "strategy_type": CategoricalSpec(
                    levels=("MaxProfit", "UnknownStrategy"),
                    probabilities=(0.5, 0.5),
                ),
            }
        )


def test_seller_population_config_rejects_probabilities_not_sum_to_one() -> None:
    with pytest.raises(ValidationError):
        SellerPopulationConfig(
            n_sellers=100,
            seed=42,
            seller_id_start=0,
            strategy_type=CategoricalSpec(
                levels=STRATEGY_TYPES,
                probabilities=(0.45, 0.40, 0.20),
            ),
            capital=DistributionSpec(
                family="lognorm",
                params={"s": 0.4, "scale": math.exp(2.5)},
            ),
            margin_floor=DistributionSpec(
                family="uniform",
                params={"loc": 0.05, "scale": 0.25},
            ),
            repricing_speed=DistributionSpec(
                family="uniform",
                params={"loc": 1.0, "scale": 5.0},
            ),
        )
