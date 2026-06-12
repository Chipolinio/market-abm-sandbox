# Назначение: DTO конфигурации сессии (Spec 008 §4.4 / Spec 009 Zone A).
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class SellerMixConfig(BaseModel):
    catboost_pct: float = Field(ge=0.0, le=1.0)
    rule_based_pct: float = Field(ge=0.0, le=1.0)
    basic_pct: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _mix_sums_to_one(self) -> SellerMixConfig:
        total = self.catboost_pct + self.rule_based_pct + self.basic_pct
        if abs(total - 1.0) > 0.01:
            raise ValueError("seller_mix percentages must sum to 1.0 (±0.01)")
        return self


class SessionConfigureRequest(BaseModel):
    n_buyers: int = Field(ge=100, le=10_000_000)
    n_sellers: int = Field(default=50, gt=0, le=1000)
    seller_mix: SellerMixConfig
    seed: int | None = None


class SessionConfigureResponse(BaseModel):
    status: str = "accepted"
    n_buyers: int
    n_sellers: int
