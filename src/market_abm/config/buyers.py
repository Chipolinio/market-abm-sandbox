from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from market_abm.config.common import CategoricalSpec, DistributionSpec
from market_abm.domain.constants import DEVICE_TYPES, PVD_SEGMENTS

ActivityHourMode = Literal["uniform_discrete"]

# Truncated normal on (-inf, 0] in standardized units.
_TRUNC_STD_NEGATIVE: dict[str, float] = {"a": float("-inf"), "b": 0.0}


def _categorical_from_domain(
    domain_levels: tuple[str, ...],
    weights: dict[str, float],
) -> CategoricalSpec:
    """Build CategoricalSpec in deterministic domain level order."""
    levels = tuple(domain_levels)
    probabilities = tuple(weights[level] for level in levels)
    return CategoricalSpec(levels=levels, probabilities=probabilities)


class BuyerPopulationConfig(BaseModel):
    """Параметры генерации синтетической популяции покупателей."""

    model_config = {"frozen": True}

    n_buyers: int = Field(gt=0, le=10_000_000)
    seed: int | None = None
    buyer_id_start: int = Field(default=0, ge=0)

    enforce_negative_coefficients: bool = True

    budget: DistributionSpec
    beta_price: DistributionSpec
    beta_delivery: DistributionSpec
    beta_rating: DistributionSpec

    device_type: CategoricalSpec
    pvd_segment: CategoricalSpec

    activity_hour: ActivityHourMode = "uniform_discrete"
    impulsive_probability: float = Field(default=0.15, ge=0.0, le=1.0)
    purchase_frequency: DistributionSpec

    ios_price_beta_multiplier: float = Field(default=0.85, gt=0.0, lt=2.0)

    @field_validator("device_type")
    @classmethod
    def device_levels_in_domain(cls, value: CategoricalSpec) -> CategoricalSpec:
        allowed = set(DEVICE_TYPES)
        if not set(value.levels).issubset(allowed):
            raise ValueError(
                f"device_type.levels должны быть подмножеством {DEVICE_TYPES}, "
                f"получено {value.levels}"
            )
        return value

    @field_validator("pvd_segment")
    @classmethod
    def pvd_levels_in_domain(cls, value: CategoricalSpec) -> CategoricalSpec:
        allowed = set(PVD_SEGMENTS)
        if not set(value.levels).issubset(allowed):
            raise ValueError(
                f"pvd_segment.levels должны быть подмножеством {PVD_SEGMENTS}, "
                f"получено {value.levels}"
            )
        return value

    @classmethod
    def default_market(
        cls,
        *,
        n_buyers: int = 10_000,
        seed: int | None = 42,
        buyer_id_start: int = 0,
    ) -> BuyerPopulationConfig:
        """Пресет e-commerce рынка по spec 001 §5.4."""
        return cls(
            n_buyers=n_buyers,
            seed=seed,
            buyer_id_start=buyer_id_start,
            enforce_negative_coefficients=True,
            budget=DistributionSpec(
                family="lognorm",
                params={"s": 0.5, "scale": math.exp(4.5)},
            ),
            beta_price=DistributionSpec(
                family="truncnorm",
                params={**_TRUNC_STD_NEGATIVE, "loc": -2.0, "scale": 0.5},
            ),
            beta_delivery=DistributionSpec(
                family="truncnorm",
                params={**_TRUNC_STD_NEGATIVE, "loc": -0.3, "scale": 0.1},
            ),
            beta_rating=DistributionSpec(
                family="truncnorm",
                params={**_TRUNC_STD_NEGATIVE, "loc": -1.5, "scale": 0.35},
            ),
            device_type=_categorical_from_domain(
                DEVICE_TYPES,
                {"ios": 0.25, "android": 0.45, "desktop": 0.30},
            ),
            pvd_segment=_categorical_from_domain(
                PVD_SEGMENTS,
                {"rich": 0.20, "standard": 0.55, "low": 0.25},
            ),
            activity_hour="uniform_discrete",
            impulsive_probability=0.15,
            purchase_frequency=DistributionSpec(
                family="uniform",
                params={"loc": 0.0, "scale": 1.0},
            ),
            ios_price_beta_multiplier=0.85,
        )
