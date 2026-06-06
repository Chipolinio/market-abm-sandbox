# Назначение файла: DTO WebSocket-стрима телеметрии (Slice 6.3 / 7.1).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from market_abm.api.schemas.events import SystemEventDTO
from market_abm.api.schemas.ticker import TickerMetricsDTO


class PriceQuantilesDTO(BaseModel):
    """Квантили цен listings на тик (approx_quantile в DuckDB)."""

    p10: float
    p50: float
    p90: float


class MarketAggregateDTO(BaseModel):
    """Агрегированные рыночные метрики за один тик."""

    mean_price: float
    total_gmv: float
    total_transactions: int
    price_quantiles: PriceQuantilesDTO | None = None


class TickStreamPayload(BaseModel):
    """Фрейм WebSocket-стрима (1Hz)."""

    tick_id: int
    timestamp_utc: str
    market_summary: MarketAggregateDTO
    ticker_metrics: TickerMetricsDTO | None = None
    active_drift_alerts: list[dict]
    events: list[SystemEventDTO] = Field(default_factory=list)
    worker_state: Literal["IDLE", "RUNNING", "PAUSED", "STOPPED", "FAILED"] = "IDLE"
