# Purpose: Validate repricing and listing init config contracts for slice 002.
# Core idea: Keep market init and repricing thresholds strongly validated.
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from market_abm.config.repricing import ListingInitConfig, RepricingConfig


def test_listing_init_default_market_builds_without_error() -> None:
    config = ListingInitConfig.default_market()
    assert isinstance(config, ListingInitConfig)


def test_listing_init_default_market_distribution_preset_matches_spec() -> None:
    config = ListingInitConfig.default_market()
    assert config.unit_cost.family == "lognorm"
    assert config.unit_cost.params["s"] == pytest.approx(0.35)
    assert config.unit_cost.params["scale"] == pytest.approx(math.exp(3.0))
    assert config.initial_margin_markup == pytest.approx(0.20)
    assert config.initial_demand_index == pytest.approx(1.0)


def test_listing_init_rejects_non_positive_markup() -> None:
    with pytest.raises(ValidationError):
        ListingInitConfig.default_market(initial_margin_markup=0.0)


def test_listing_init_rejects_negative_initial_demand() -> None:
    with pytest.raises(ValidationError):
        ListingInitConfig.default_market(initial_demand_index=-0.01)


def test_repricing_default_market_builds_without_error() -> None:
    config = RepricingConfig.default_market()
    assert isinstance(config, RepricingConfig)


def test_repricing_default_market_values_match_spec() -> None:
    config = RepricingConfig.default_market()
    assert config.relative_step == pytest.approx(0.02)
    assert config.max_profit_demand_high == pytest.approx(1.10)
    assert config.max_profit_demand_low == pytest.approx(0.90)
    assert config.max_volume_aggression == pytest.approx(1.2)
    assert config.min_listing_price == pytest.approx(25.0)


def test_repricing_rejects_invalid_relative_step() -> None:
    with pytest.raises(ValidationError):
        RepricingConfig(relative_step=0.0)
    with pytest.raises(ValidationError):
        RepricingConfig(relative_step=0.51)


def test_repricing_rejects_invalid_thresholds_and_aggression() -> None:
    with pytest.raises(ValidationError):
        RepricingConfig(max_profit_demand_high=1.0)
    with pytest.raises(ValidationError):
        RepricingConfig(max_profit_demand_low=1.0)
    with pytest.raises(ValidationError):
        RepricingConfig(max_volume_aggression=0.99)
