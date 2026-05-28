# Purpose: Define validated seller population config for slice 002.
# Core idea: Keep all seller generation parameters in immutable Pydantic models.
from __future__ import annotations

import math

from pydantic import BaseModel, Field, field_validator

from market_abm.config.buyers import CategoricalSpec, DistributionSpec
from market_abm.domain.constants import STRATEGY_TYPES


class SellerPopulationConfig(BaseModel):
    """Validated inputs for vectorized sellers_df generation."""

    model_config = {"frozen": True}

    n_sellers: int = Field(gt=0, le=1_000_000)
    seed: int | None = None
    seller_id_start: int = Field(default=0, ge=0)

    strategy_type: CategoricalSpec
    capital: DistributionSpec
    margin_floor: DistributionSpec
    repricing_speed: DistributionSpec

    @field_validator("strategy_type")
    @classmethod
    def strategy_levels_in_domain(cls, value: CategoricalSpec) -> CategoricalSpec:
        allowed = set(STRATEGY_TYPES)
        if not set(value.levels).issubset(allowed):
            raise ValueError(
                f"strategy_type.levels must be subset of {STRATEGY_TYPES}, "
                f"got {value.levels}"
            )
        return value

    @classmethod
    def default_market(
        cls,
        *,
        n_sellers: int = 1_000,
        seed: int | None = 42,
        seller_id_start: int = 0,
    ) -> SellerPopulationConfig:
        """Build default seller preset aligned with spec 002."""
        return cls(
            n_sellers=n_sellers,
            seed=seed,
            seller_id_start=seller_id_start,
            strategy_type=CategoricalSpec(
                levels=STRATEGY_TYPES,
                probabilities=(0.45, 0.40, 0.15),
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
