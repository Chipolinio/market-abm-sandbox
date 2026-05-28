# Purpose: Validate shared config specs after extraction to config/common.py.
# Core idea: Keep backward-compatible imports while centralizing shared models.
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from market_abm.config.buyers import CategoricalSpec as BuyersCategoricalSpec
from market_abm.config.buyers import DistributionSpec as BuyersDistributionSpec
from market_abm.config.common import CategoricalSpec, DistributionSpec


def test_distribution_spec_available_from_common_and_buyers_alias() -> None:
    common = DistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(1.0)})
    alias = BuyersDistributionSpec(family="lognorm", params={"s": 0.5, "scale": math.exp(1.0)})
    assert common.family == alias.family
    assert common.params == alias.params


def test_categorical_spec_available_from_common_and_buyers_alias() -> None:
    common = CategoricalSpec(levels=("a", "b"), probabilities=(0.5, 0.5))
    alias = BuyersCategoricalSpec(levels=("a", "b"), probabilities=(0.5, 0.5))
    assert common.levels == alias.levels
    assert common.probabilities == alias.probabilities


def test_common_distribution_spec_validates_scipy_params() -> None:
    with pytest.raises(ValidationError):
        DistributionSpec(family="lognorm", params={"bad_param": 1.0})
