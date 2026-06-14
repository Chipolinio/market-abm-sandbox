# Назначение файла: DTO ticker metrics и market leaders (Slice 8.3).
from __future__ import annotations

from pydantic import BaseModel, Field


class TickerMetricsDTO(BaseModel):
    active_sellers_count: int
    total_non_bankrupt_sellers: int
    total_market_gmv: float
    market_price_index: float
    current_tick: int


class MarketLeaderRowDTO(BaseModel):
    seller_id: int
    working_capital: float
    tick_revenue: float
    cumulative_revenue: float
    is_bankrupt: bool
    strategy_type: str | None = None
    algorithm_type: str = "RULE"
    inventory_stock: int = 0
    logic_status: str = "rule_based"


class MarketLeadersResponse(BaseModel):
    run_id: str
    tick_id: int
    leaders: list[MarketLeaderRowDTO]


class DemandMatrixCellDTO(BaseModel):
    row: int
    col: int
    density: float


class DemandMatrixResponse(BaseModel):
    run_id: str
    tick_id: int
    grid_size: int = 3
    row_count: int = 3
    col_count: int = 3
    x_labels: list[str] = Field(default_factory=list)
    y_labels: list[str] = Field(default_factory=list)
    axis_x: str = "strategy_type"
    axis_y: str = "pvd_segment"
    cells: list[DemandMatrixCellDTO] = Field(default_factory=list)
