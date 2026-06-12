# Назначение файла: Pydantic-конфиг экономики селлеров (Slice 8.2).
from __future__ import annotations

from pydantic import BaseModel, Field


class SellerEconomicsConfig(BaseModel):
    """Параметры settle_seller_economics за тик."""

    fixed_cost_per_tick: float = Field(default=1.0, ge=0.0)
    bankruptcy_threshold: float = Field(default=0.0)
    allow_negative_capital_carry: bool = Field(default=False)
