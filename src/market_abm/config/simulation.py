# Назначение файла: хранить конфиги одного шага симуляции рынка.
# Базовая идея: все параметры шага и выбора задаются через Pydantic-модели.
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.inventory import (
    InventoryConfig,
    InventoryPricingConfig,
    ReplenishmentConfig,
)
from market_abm.config.ranking import RankingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import PVD_SEGMENTS


class DynamicRatingConfig(BaseModel):
    """EMA rating update from seed-aware transaction reviews (Spec 012 §6).

    Rating_j,t = (1−γ)·Rating_j,t−1 + γ·Score_tx
    Score_tx ~ U(score_min, score_max) adjusted for price-vs-cat-median penalty.
    """

    model_config = {"frozen": True}

    enabled: bool = True
    gamma: float = Field(default=0.08, gt=0.0, le=1.0, description="EMA smoothing factor")
    score_min: float = Field(default=1.0, ge=0.0)
    score_max: float = Field(default=5.0, ge=0.0)
    price_penalty_scale: float = Field(
        default=2.0,
        ge=0.0,
        description="Max score penalty when price = 2× cat_median; linear in (ratio-1)",
    )


class ReferencePriceConfig(BaseModel):
    """Reference-price penalty term in MNL utility (Spec 012 §3.2).

    U_j += β_ref · (-max(0, log(p_j / p_ref))^2)

    Enabled by default after Spec 012; set enabled=False for backward compat / ablation.
    """

    model_config = {"frozen": True}

    enabled: bool = True
    beta_ref: float = Field(
        default=1.0,
        gt=0.0,
        description="Weight for the reference-price penalty term",
    )
    window_ticks: int = Field(
        default=20,
        ge=1,
        description="Rolling window for p50_hist_cat computation (future per-category use)",
    )


class ChoiceModelConfig(BaseModel):
    """Параметры модели выбора покупателя в одном шаге."""

    model_config = {"frozen": True}

    engine: Literal["choice_learn", "numpy_softmax"] = "choice_learn"
    outside_utility_bias: float = -1.5
    outside_utility_bias_by_pvd_segment: dict[str, float] | None = None
    income_utility_gamma: float = Field(
        default=0.35,
        ge=0.0,
        le=5.0,
        description="γ in U += γ·log(budget/budget_baseline)",
    )
    max_products_per_choice_set: int = Field(default=200, gt=1, le=10_000)
    buyers_batch_size: int = Field(default=5_000, gt=100, le=100_000)
    reference_price: ReferencePriceConfig = Field(default_factory=ReferencePriceConfig)
    ranking: RankingConfig = Field(default_factory=RankingConfig)

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
        """
        Bias outside-option в шкале utility (β·price + …).
        Должен быть существенно ниже типичной utility карточки (~−30…−80),
        иначе softmax всегда выбирает отказ и GMV остаётся нулевым.
        """
        return {
            "rich": -120.0,
            "standard": -100.0,
            "low": -80.0,
        }


class SimulationStepConfig(BaseModel):
    """Параметры одного шага симуляции."""

    model_config = {"frozen": True}

    tick_id: int = Field(default=0, ge=0)
    seed: int | None = None
    choice: ChoiceModelConfig = Field(default_factory=ChoiceModelConfig)
    repricing: RepricingConfig = Field(default_factory=RepricingConfig.default_market)
    economics: SellerEconomicsConfig = Field(default_factory=SellerEconomicsConfig)
    rating: DynamicRatingConfig = Field(default_factory=DynamicRatingConfig)
    inventory: InventoryConfig = Field(default_factory=InventoryConfig)
    inventory_pricing: InventoryPricingConfig = Field(default_factory=InventoryPricingConfig)
    replenishment: ReplenishmentConfig = Field(default_factory=ReplenishmentConfig)
