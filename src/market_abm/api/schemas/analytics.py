# Назначение файла: DTO REST-эндпоинтов аналитики / backfill (Slice 7.1).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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


class ListingMetricPointDTO(BaseModel):
    """Метрики одного listing на тик (dense charts, Slice 7.7)."""

    tick_id: int
    price: float | None
    gmv: float
    volume: int


class ListingSeriesDTO(BaseModel):
    """Временной ряд одного SKU из топ-N."""

    listing_id: int
    seller_id: int
    points: list[ListingMetricPointDTO]


class TopListingsResponse(BaseModel):
    """Ответ GET /api/v1/analytics/top-listings."""

    run_id: str
    listings: list[ListingSeriesDTO]


# --- Spec 014 §6–§7 ---


class SegmentRowDTO(BaseModel):
    segment: Literal["rich", "standard", "low"]
    n_buyers: int
    n_active: int
    mean_budget_effective: float
    mean_budget_baseline: float
    mean_freq_effective: float
    mean_scar_factor: float
    churn_share: float


class SegmentHealthResponse(BaseModel):
    run_id: str
    tick_id: int
    rows: list[SegmentRowDTO] = Field(default_factory=list)


class StrategyPulseRowDTO(BaseModel):
    strategy_type: str
    avg_demand_index: float
    n_listings: int = 0


class StrategyPulseResponse(BaseModel):
    run_id: str
    tick_id: int
    panic_active: bool = False
    strategies: list[StrategyPulseRowDTO] = Field(default_factory=list)


class ListingRankingBreakdownDTO(BaseModel):
    seller_id: int
    listing_id: int
    w1: float
    w2: float
    w3: float
    rating: float
    price_term: float
    sales_term: float
    term_rating: float
    term_price: float
    term_sales: float
    score: float


class CategoryRankingRowDTO(BaseModel):
    category_id: int
    n_listings: int
    median_score: float
    median_price: float
    sales_window_sum: float
    top_listing_ids: list[int] = Field(default_factory=list)


class CategoryRankingResponse(BaseModel):
    run_id: str
    tick_id: int
    rows: list[CategoryRankingRowDTO] = Field(default_factory=list)
