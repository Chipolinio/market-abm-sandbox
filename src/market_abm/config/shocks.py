# Назначение файла: Pydantic-конфиг каталога эффектов шоков (Slice 8.1).
from __future__ import annotations

from pydantic import BaseModel, Field


class ShockEffectSpec(BaseModel):
    """Параметры эффекта по типу шока."""

    budget_multiplier: float = Field(default=0.7, gt=0.0, le=2.0)
    fee_delta: float = Field(default=0.05, ge=0.0, le=0.5)
    supply_cost_multiplier: float = Field(default=1.2, gt=0.0, le=3.0)


class ShockCatalogConfig(BaseModel):
    """Каталог предустановленных эффектов v1."""

    demand_crash: ShockEffectSpec = ShockEffectSpec(budget_multiplier=0.7)
    demand_boom: ShockEffectSpec = ShockEffectSpec(budget_multiplier=1.3)
    platform_fee_hike: ShockEffectSpec = ShockEffectSpec(fee_delta=0.05)
    platform_fee_cut: ShockEffectSpec = ShockEffectSpec(fee_delta=0.05)
    supply_shock: ShockEffectSpec = ShockEffectSpec(supply_cost_multiplier=1.2)
