# Назначение файла: runtime-лимиты ML inference в live worker (Spec 011 §5A.3).
from __future__ import annotations

from pydantic import BaseModel, Field


class MlRuntimeConfig(BaseModel):
    """Бюджет inferencing CatBoost в hot path step()."""

    model_config = {"frozen": True}

    inference_timeout_ms: float = Field(default=50.0, gt=0.0, le=60_000.0)
    fallback_to_rules_on_timeout: bool = True
    max_listings_per_ml_tick: int = Field(default=5_000, gt=0, le=1_000_000)
