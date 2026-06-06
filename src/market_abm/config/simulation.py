# Назначение файла: хранить конфиги одного шага симуляции рынка.
# Базовая идея: все параметры шага и выбора задаются через Pydantic-модели.
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import PVD_SEGMENTS


class ChoiceModelConfig(BaseModel):
    """Параметры модели выбора покупателя в одном шаге."""

    model_config = {"frozen": True}

    engine: Literal["choice_learn", "numpy_softmax"] = "choice_learn"
    outside_utility_bias: float = -1.5
    outside_utility_bias_by_pvd_segment: dict[str, float] | None = None
    max_products_per_choice_set: int = Field(default=200, gt=1, le=10_000)
    buyers_batch_size: int = Field(default=5_000, gt=100, le=100_000)

    @model_validator(mode="after")
    def _validate_segment_keys(self) -> Self:
        if self.outside_utility_bias_by_pvd_segment is None:
            return self
        unknown = set(self.outside_utility_bias_by_pvd_segment) - set(PVD_SEGMENTS)
        if unknown:
            raise ValueError(f"Unknown pvd_segment keys: {sorted(unknown)}")
        return self

    @classmethod
    def default_segment_biases(cls) -> dict[str, float]:
        """Стартовые bias по сегменту ПВЗ для калибровки отказа от покупки."""
        return {
            "rich": -2.5,
            "standard": -1.5,
            "low": -0.5,
        }


class SimulationStepConfig(BaseModel):
    """Параметры одного шага симуляции."""

    model_config = {"frozen": True}

    tick_id: int = Field(default=0, ge=0)
    seed: int | None = None
    choice: ChoiceModelConfig = Field(default_factory=ChoiceModelConfig)
    repricing: RepricingConfig = Field(default_factory=RepricingConfig.default_market)
    economics: SellerEconomicsConfig = Field(default_factory=SellerEconomicsConfig)
