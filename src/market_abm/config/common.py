# Purpose: Provide shared Pydantic specs for distribution and categorical sampling.
# Core idea: Centralize reusable config models for buyers, sellers, and simulation layers.
from __future__ import annotations

import math
from typing import Any, Literal, Self

import scipy.stats
from pydantic import BaseModel, model_validator

DistributionFamily = Literal["lognorm", "norm", "truncnorm", "gamma", "uniform"]


def _build_scipy_distribution(family: str, params: dict[str, float]) -> Any:
    """Validate that scipy.stats accepts family and params."""
    return getattr(scipy.stats, family)(**params)


class DistributionSpec(BaseModel):
    """Specification for one continuous distribution used in vectorized sampling."""

    model_config = {"frozen": True}

    family: DistributionFamily
    params: dict[str, float]

    @model_validator(mode="after")
    def scipy_params_are_valid(self) -> Self:
        try:
            _build_scipy_distribution(self.family, self.params)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                f"Invalid scipy.stats.{self.family} params: {self.params!r}"
            ) from exc
        return self


class CategoricalSpec(BaseModel):
    """Discrete categorical distribution for DataFrame category columns."""

    model_config = {"frozen": True}

    levels: tuple[str, ...]
    probabilities: tuple[float, ...]

    @model_validator(mode="after")
    def levels_match_probabilities(self) -> Self:
        if len(self.levels) != len(self.probabilities):
            raise ValueError(
                "levels length must match probabilities length: "
                f"{len(self.levels)} != {len(self.probabilities)}"
            )
        if any(p < 0 for p in self.probabilities):
            raise ValueError("probabilities must be non-negative")
        total = sum(self.probabilities)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"probabilities must sum to 1.0, got {total}")
        return self
