from __future__ import annotations

import math
from typing import Any, Literal, Self

import scipy.stats
from pydantic import BaseModel, Field, field_validator, model_validator

from market_abm.domain.constants import DEVICE_TYPES, PVD_SEGMENTS

DistributionFamily = Literal["lognorm", "norm", "truncnorm", "gamma", "uniform"]
ActivityHourMode = Literal["uniform_discrete"]

_SUPPORTED_FAMILIES: frozenset[str] = frozenset(
    {"lognorm", "norm", "truncnorm", "gamma", "uniform"}
)

# Усечённая нормаль на (-inf, 0] в стандартных единицах → β < 0 после loc + scale * Z.
_TRUNC_STD_NEGATIVE: dict[str, float] = {"a": float("-inf"), "b": 0.0}


def _build_scipy_distribution(family: str, params: dict[str, float]) -> Any:
    """Проверяет, что scipy.stats принимает family и params (чистая валидация)."""
    return getattr(scipy.stats, family)(**params)


class DistributionSpec(BaseModel):
    """Спецификация одного непрерывного распределения для векторного сэмпла."""

    model_config = {"frozen": True}

    family: DistributionFamily
    params: dict[str, float]

    @model_validator(mode="after")
    def scipy_params_are_valid(self) -> Self:
        try:
            _build_scipy_distribution(self.family, self.params)
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError(
                f"Невалидные параметры scipy.stats.{self.family}: {self.params!r}"
            ) from exc
        return self


class CategoricalSpec(BaseModel):
    """Дискретное распределение уровней категориальной колонки buyers_df."""

    model_config = {"frozen": True}

    levels: tuple[str, ...]
    probabilities: tuple[float, ...]

    @model_validator(mode="after")
    def levels_match_probabilities(self) -> Self:
        if len(self.levels) != len(self.probabilities):
            raise ValueError(
                "Число levels должно совпадать с числом probabilities: "
                f"{len(self.levels)} != {len(self.probabilities)}"
            )
        if any(p < 0 for p in self.probabilities):
            raise ValueError("Вероятности не могут быть отрицательными")
        total = sum(self.probabilities)
        if not math.isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-6):
            raise ValueError(f"Сумма probabilities должна быть 1.0, получено {total}")
        return self


def _categorical_from_domain(
    domain_levels: tuple[str, ...],
    weights: dict[str, float],
) -> CategoricalSpec:
    """Собирает CategoricalSpec в порядке доменных уровней (детерминированный контракт)."""
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
                params={"s": 0.5, "scale": math.exp(3.0)},
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
                params={**_TRUNC_STD_NEGATIVE, "loc": -0.5, "scale": 0.2},
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
