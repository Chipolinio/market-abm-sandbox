# Назначение файла: Pydantic-конфиг каталога эффектов шоков (Slice 8.1, Spec 010 §10.2).
from __future__ import annotations

from pydantic import BaseModel, Field


class ShockEffectSpec(BaseModel):
    """Параметры эффекта по типу шока."""

    model_config = {"frozen": True}

    budget_multiplier: float = Field(default=0.7, gt=0.0, le=2.0)
    purchase_frequency_multiplier: float = Field(default=0.7, gt=0.0, le=2.0)
    scale_purchase_frequency: bool = Field(default=True)
    fee_delta: float = Field(default=0.05, ge=0.0, le=0.5)
    supply_cost_multiplier: float = Field(default=1.2, gt=0.0, le=3.0)


class ShockCatalogConfig(BaseModel):
    """Каталог предустановленных эффектов v1."""

    model_config = {"frozen": True}

    demand_crash: ShockEffectSpec = ShockEffectSpec(
        budget_multiplier=0.7,
        purchase_frequency_multiplier=0.7,
    )
    demand_boom: ShockEffectSpec = ShockEffectSpec(
        budget_multiplier=1.3,
        purchase_frequency_multiplier=1.3,
    )
    platform_fee_hike: ShockEffectSpec = ShockEffectSpec(
        fee_delta=0.05,
        scale_purchase_frequency=False,
    )
    platform_fee_cut: ShockEffectSpec = ShockEffectSpec(
        fee_delta=0.05,
        scale_purchase_frequency=False,
    )
    marketplace_promotion: ShockEffectSpec = ShockEffectSpec(
        fee_delta=0.10,
        scale_purchase_frequency=False,
    )
    supply_shock: ShockEffectSpec = ShockEffectSpec(
        supply_cost_multiplier=1.2,
        scale_purchase_frequency=False,
    )
