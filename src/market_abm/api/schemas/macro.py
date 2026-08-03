# Spec 014 §4.1 — macro / active shock DTOs for WS payload.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MacroStateDTO(BaseModel):
    """Serialized MacroState + caps for FE stress/expansion bars."""

    model_config = {"frozen": True}

    regime: Literal["normal", "stress", "expansion", "recovery"]
    stress: float
    expansion: float
    stress_cap: float
    expansion_cap: float
    episode_id: int
    ticks_in_episode: int
    peak_stress: float
    peak_expansion: float
    est_recovery_eta_ticks: int | None = None


class ActiveShockDTO(BaseModel):
    """One entry from SimulationContext.active_shocks."""

    model_config = {"frozen": True}

    shock_type: str
    intensity: float
    remaining_ticks: int | None = None
    applied_at_tick: int
    scenario: Literal["mild", "standard", "severe"] | None = None
