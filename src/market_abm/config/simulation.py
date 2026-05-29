# Назначение файла: хранить конфиги одного шага симуляции рынка.
# Базовая идея: все параметры шага и выбора задаются через Pydantic-модели.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from market_abm.config.repricing import RepricingConfig


class ChoiceModelConfig(BaseModel):
    """Параметры модели выбора покупателя в одном шаге."""

    model_config = {"frozen": True}

    engine: Literal["choice_learn", "numpy_softmax"] = "choice_learn"
    outside_utility_bias: float = -1.5
    max_products_per_choice_set: int = Field(default=200, gt=1, le=10_000)
    buyers_batch_size: int = Field(default=5_000, gt=100, le=100_000)


class SimulationStepConfig(BaseModel):
    """Параметры одного шага симуляции."""

    model_config = {"frozen": True}

    tick_id: int = Field(default=0, ge=0)
    seed: int | None = None
    choice: ChoiceModelConfig = Field(default_factory=ChoiceModelConfig)
    repricing: RepricingConfig = Field(default_factory=RepricingConfig.default_market)
