# Назначение файла: Pydantic DTO REST shock API (Slice 8.1).
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
    duration_ticks: int = Field(default=10, ge=1, le=10_000)


class SimulationShockResponse(BaseModel):
    status: Literal["queued"] = "queued"
    shock_type: str
    queue_depth: int
