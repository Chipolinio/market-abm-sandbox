# Назначение файла: DTO REST-эндпоинтов аналитики / backfill (Slice 7.1).
from __future__ import annotations

from pydantic import BaseModel


class PriceIndexPointDTO(BaseModel):
    """Одна точка рыночного индекса цен по tick_id."""

    tick_id: int
    p10: float | None
    p50: float | None
    p90: float | None
    mean_price: float | None


class PriceIndexResponse(BaseModel):
    """Ответ GET /api/v1/analytics/price-index."""

    run_id: str
    points: list[PriceIndexPointDTO]


class GmvPointDTO(BaseModel):
    """GMV и число транзакций за тик."""

    tick_id: int
    gmv: float
    transaction_count: int


class GmvByTickResponse(BaseModel):
    """Ответ GET /api/v1/analytics/gmv-by-tick."""

    run_id: str
    points: list[GmvPointDTO]
