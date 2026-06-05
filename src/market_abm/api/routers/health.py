# Назначение файла: лёгкий healthcheck для Docker Compose (Slice 7.1).
# Базовая идея: без DuckDB, воркера и AnalyticsStore.
from __future__ import annotations

from fastapi import APIRouter

from market_abm.api.schemas.health import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Проверка готовности Uvicorn; используется Docker healthcheck."""
    return HealthResponse()
