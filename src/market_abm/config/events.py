# Назначение файла: Pydantic-конфиг детектора system_events (Slice 8.3).
from __future__ import annotations

from pydantic import BaseModel, Field


class CollusionDetectorConfig(BaseModel):
    window_ticks: int = Field(default=20, ge=5, le=200)
    min_correlation: float = Field(default=0.9, gt=0.0, le=1.0)
    min_observations: int = Field(default=15, ge=5)


class FlashCrashDetectorConfig(BaseModel):
    window_ticks: int = Field(default=10, ge=3, le=100)
    median_drop_pct: float = Field(default=0.40, gt=0.0, le=1.0)


class SystemEventsConfig(BaseModel):
    check_every_n_ticks: int = Field(default=1, ge=1)
    collusion: CollusionDetectorConfig = CollusionDetectorConfig()
    flash_crash: FlashCrashDetectorConfig = FlashCrashDetectorConfig()
