# Назначение файла: DTO управления симуляцией (REST Control, Slice 6.2).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SimulationStartRequest(BaseModel):
    """Тело запроса POST /api/v1/simulation/start."""

    run_id: str | None = None
    n_buyers: int = Field(default=1000, gt=0, le=100_000)
    n_sellers: int = Field(default=50, gt=0, le=1000)
    repricing_mode: Literal["rules", "catboost", "hybrid"] = "rules"
    force_clear: bool = Field(
        default=False,
        description="Очистить Parquet-логи перед стартом новой сессии",
    )


class SimulationStatusResponse(BaseModel):
    """Тело ответа GET /api/v1/simulation/status."""

    run_id: str
    state: Literal["IDLE", "RUNNING", "PAUSED", "STOPPED", "FAILED"]
    current_tick: int
    elapsed_time_seconds: float
    last_error: str | None = None
