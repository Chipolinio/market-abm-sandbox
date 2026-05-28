# Purpose: Define validated configs for listings initialization and repricing tick.
# Core idea: Keep simulation thresholds immutable and spec-aligned in config layer.
from __future__ import annotations

import math

from pydantic import BaseModel, Field

from market_abm.config.buyers import DistributionSpec
from market_abm.domain.constants import (
    DEFAULT_DEMAND_INDEX,
    MAX_PROFIT_DEMAND_HIGH_DEFAULT,
    MAX_PROFIT_DEMAND_LOW_DEFAULT,
    MAX_VOLUME_AGGRESSION_DEFAULT,
)


class ListingInitConfig(BaseModel):
    """Validated parameters for initial listings_df construction."""

    model_config = {"frozen": True}

    unit_cost: DistributionSpec
    initial_margin_markup: float = Field(default=0.20, gt=0.0)
    initial_demand_index: float = Field(default=DEFAULT_DEMAND_INDEX, ge=0.0)

    @classmethod
    def default_market(
        cls,
        *,
        initial_margin_markup: float = 0.20,
        initial_demand_index: float = DEFAULT_DEMAND_INDEX,
    ) -> ListingInitConfig:
        """Build default listing initialization preset for slice 002."""
        return cls(
            unit_cost=DistributionSpec(
                family="lognorm",
                params={"s": 0.3, "scale": math.exp(1.5)},
            ),
            initial_margin_markup=initial_margin_markup,
            initial_demand_index=initial_demand_index,
        )


class RepricingConfig(BaseModel):
    """Validated thresholds controlling one repricing tick."""

    model_config = {"frozen": True}

    relative_step: float = Field(default=0.02, gt=0.0, le=0.5)
    max_profit_demand_high: float = Field(
        default=MAX_PROFIT_DEMAND_HIGH_DEFAULT,
        gt=1.0,
    )
    max_profit_demand_low: float = Field(
        default=MAX_PROFIT_DEMAND_LOW_DEFAULT,
        gt=0.0,
        lt=1.0,
    )
    max_volume_aggression: float = Field(
        default=MAX_VOLUME_AGGRESSION_DEFAULT,
        ge=1.0,
    )

    @classmethod
    def default_market(cls) -> RepricingConfig:
        """Build default repricing preset aligned with spec 002."""
        return cls(
            relative_step=0.02,
            max_profit_demand_high=MAX_PROFIT_DEMAND_HIGH_DEFAULT,
            max_profit_demand_low=MAX_PROFIT_DEMAND_LOW_DEFAULT,
            max_volume_aggression=MAX_VOLUME_AGGRESSION_DEFAULT,
        )
