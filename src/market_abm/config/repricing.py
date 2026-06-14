# Purpose: Define validated configs for listings initialization and repricing tick.
# Core idea: Keep simulation thresholds immutable and spec-aligned in config layer.
from __future__ import annotations

import math
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from market_abm.config.common import DistributionSpec
from market_abm.config.ml_repricing import CatBoostRepricingConfig
from market_abm.domain.constants import (
    DEFAULT_DEMAND_INDEX,
    MAX_PROFIT_DEMAND_HIGH_DEFAULT,
    MAX_PROFIT_DEMAND_LOW_DEFAULT,
    MAX_VOLUME_AGGRESSION_DEFAULT,
    MIN_LISTING_PRICE_DEFAULT,
)

# Режимы репрайсинга (Spec 005 §1.4 / §8.2). Default — rules (обратная совместимость 002–004).
RepricingMode = Literal["rules", "catboost", "hybrid"]


class StressRepricingConfig(BaseModel):
    """Stress-dependent repricing multipliers (Spec 011 §5.3)."""

    model_config = {"frozen": True}

    stress_repricing_threshold: float = Field(default=0.15, ge=0.0, le=2.0)
    stress_step_gain: float = Field(default=2.0, ge=0.0, le=10.0)
    stress_volume_gain: float = Field(default=1.5, ge=0.0, le=10.0)
    stress_dead_zone_shrink: float = Field(default=0.05, ge=0.0, le=0.5)
    panic_margin_above_unit_cost: float = Field(default=0.05, ge=0.0)
    forbid_price_below_unit_cost: bool = True


class ListingInitConfig(BaseModel):
    """Validated parameters for initial listings_df construction."""

    model_config = {"frozen": True}

    unit_cost: DistributionSpec
    initial_margin_markup: float = Field(default=0.20, gt=0.0)
    initial_demand_index: float = Field(default=DEFAULT_DEMAND_INDEX, ge=0.0)
    minimum_price_to_floor_ratio: float = Field(default=1.0, ge=1.0, le=2.0)

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
                params={"s": 0.35, "scale": math.exp(3.0)},
            ),
            initial_margin_markup=initial_margin_markup,
            initial_demand_index=initial_demand_index,
        )

    @classmethod
    def market_with_headroom(cls) -> ListingInitConfig:
        """Headroom preset: выше markup и запас над p_min для crash repricing (§5.2)."""
        return cls(
            unit_cost=DistributionSpec(
                family="lognorm",
                params={"s": 0.35, "scale": math.exp(3.0)},
            ),
            initial_margin_markup=0.35,
            initial_demand_index=DEFAULT_DEMAND_INDEX,
            minimum_price_to_floor_ratio=1.15,
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
    min_listing_price: float = Field(default=MIN_LISTING_PRICE_DEFAULT, ge=0.0)
    mode: RepricingMode = "rules"
    warmup_ticks: int = Field(default=15, ge=0)
    ml: CatBoostRepricingConfig | None = None
    stress: StressRepricingConfig = Field(default_factory=StressRepricingConfig)

    @model_validator(mode="after")
    def _validate_ml_mode(self) -> Self:
        """ML-режимы требуют ml-конфиг и включённый exploration в prod-пути (Spec 005 §8.2, §13)."""
        if self.mode in ("catboost", "hybrid"):
            if self.ml is None:
                raise ValueError(
                    f"repricing.mode={self.mode!r} requires 'ml' config (CatBoostRepricingConfig)"
                )
            if not self.ml.exploration.enabled:
                raise ValueError(
                    "ML repricing requires exploration.enabled=True (anti-stagnation, §4.3.2)"
                )
        return self

    @classmethod
    def default_market(cls) -> RepricingConfig:
        """Build default repricing preset aligned with spec 002."""
        return cls(
            relative_step=0.02,
            max_profit_demand_high=MAX_PROFIT_DEMAND_HIGH_DEFAULT,
            max_profit_demand_low=MAX_PROFIT_DEMAND_LOW_DEFAULT,
            max_volume_aggression=MAX_VOLUME_AGGRESSION_DEFAULT,
            min_listing_price=MIN_LISTING_PRICE_DEFAULT,
        )

    @classmethod
    def market_with_headroom(cls) -> RepricingConfig:
        """Headroom preset: ниже absolute floor для crash repricing (Spec 011 §5.2)."""
        return cls(
            relative_step=0.02,
            max_profit_demand_high=MAX_PROFIT_DEMAND_HIGH_DEFAULT,
            max_profit_demand_low=MAX_PROFIT_DEMAND_LOW_DEFAULT,
            max_volume_aggression=MAX_VOLUME_AGGRESSION_DEFAULT,
            min_listing_price=5.0,
        )
