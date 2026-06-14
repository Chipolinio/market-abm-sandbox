# Назначение файла: Pydantic DTO REST shock API (Slice 8.1 / Spec 011 §8.4).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SimulationShockRequest(BaseModel):
    shock_type: Literal[
        "demand_crash",
        "demand_boom",
        "platform_fee_hike",
        "platform_fee_cut",
        "marketplace_promotion",
        "supply_shock",
    ]
    intensity: float = Field(default=1.0, gt=0.0, le=3.0)
    duration_ticks: int | None = Field(default=None, ge=1, le=10_000)
    scenario: Literal["mild", "standard", "severe"] | None = "standard"
    shock_mode: Literal["stochastic_regime", "fixed_duration"] | None = None


class SimulationShockResponse(BaseModel):
    status: Literal["queued"] = "queued"
    shock_type: str
    queue_depth: int
