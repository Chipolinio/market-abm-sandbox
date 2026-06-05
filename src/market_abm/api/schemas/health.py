# Назначение файла: DTO healthcheck для Docker Compose (Slice 7.1).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Ответ GET /api/v1/health — без обращения к DuckDB."""

    status: Literal["ok"] = "ok"
