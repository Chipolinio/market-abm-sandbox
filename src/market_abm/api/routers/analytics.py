# Назначение файла: REST read-only аналитика для UI backfill (Slice 7.1).
# Базовая идея: читает AnalyticsStore через app.state; CQRS query-side.
from __future__ import annotations

from typing import Any

import polars as pl
from fastapi import APIRouter, Depends, Query, Request

from market_abm.analytics.store import AnalyticsStore
from market_abm.api.schemas.analytics import (
    GmvByTickResponse,
    GmvPointDTO,
    ListingMetricPointDTO,
    ListingSeriesDTO,
    PriceIndexPointDTO,
    PriceIndexResponse,
    TopListingsResponse,
)
from market_abm.analytics.leaders import query_demand_matrix, query_market_leaders
from market_abm.api.schemas.events import SystemEventDTO, SystemEventsResponse
from market_abm.api.schemas.stream import MarketAggregateDTO, PriceQuantilesDTO
from market_abm.api.schemas.ticker import (
    DemandMatrixCellDTO,
    DemandMatrixResponse,
    MarketLeaderRowDTO,
    MarketLeadersResponse,
)
from market_abm.domain.constants import COL_LISTING_ID, COL_SELLER_ID, COL_TICK_ID

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])

_DEFAULT_RUN_ID = "default"


def _get_analytics_store(request: Request) -> AnalyticsStore | None:
    """Возвращает инжектированный store или None, если артефакты ещё не созданы."""
    injected: AnalyticsStore | None = getattr(request.app.state, "analytics_store", None)
    if injected is not None:
        return injected

    artifacts_dir: str | None = getattr(request.app.state, "artifacts_dir", None)
    if artifacts_dir is None:
        return None

    from pathlib import Path

    run_root = Path(artifacts_dir)
    if not (run_root / "manifest.json").is_file():
        return None

    return AnalyticsStore(run_root)


def _run_id_from_store(store: AnalyticsStore | None) -> str:
    if store is None:
        return _DEFAULT_RUN_ID
    return store._run_id_from_manifest()


def _market_aggregate_from_store(store: AnalyticsStore, tick_id: int) -> MarketAggregateDTO:
    agg: dict[str, Any] = store.query_market_aggregate(tick_id)
    raw_q = agg.get("price_quantiles")
    quantiles: PriceQuantilesDTO | None = None
    if isinstance(raw_q, dict):
        quantiles = PriceQuantilesDTO(
            p10=float(raw_q["p10"]),
            p50=float(raw_q["p50"]),
            p90=float(raw_q["p90"]),
        )
    return MarketAggregateDTO(
        mean_price=float(agg["mean_price"]),
        total_gmv=float(agg["total_gmv"]),
        total_transactions=int(agg["total_transactions"]),
        price_quantiles=quantiles,
    )


@router.get("/price-index", response_model=PriceIndexResponse)
async def get_price_index(
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> PriceIndexResponse:
    """Исторический ряд квантилей цен по tick_id (backfill для графика)."""
    if store is None:
        return PriceIndexResponse(run_id=_DEFAULT_RUN_ID, points=[])

    df = store.price_index_by_tick()
    points = [
        PriceIndexPointDTO(
            tick_id=int(row[COL_TICK_ID]),
            p10=row["p10_price"],
            p50=row["median_price"],
            p90=row["p90_price"],
            mean_price=row["mean_price"],
        )
        for row in df.iter_rows(named=True)
    ]
    return PriceIndexResponse(run_id=_run_id_from_store(store), points=points)


@router.get("/gmv-by-tick", response_model=GmvByTickResponse)
async def get_gmv_by_tick(
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> GmvByTickResponse:
    """Исторический ряд GMV по tick_id."""
    if store is None:
        return GmvByTickResponse(run_id=_DEFAULT_RUN_ID, points=[])

    df = store.gmv_by_tick()
    points = [
        GmvPointDTO(
            tick_id=int(row[COL_TICK_ID]),
            gmv=float(row["gmv"]),
            transaction_count=int(row["transaction_count"]),
        )
        for row in df.iter_rows(named=True)
    ]
    return GmvByTickResponse(run_id=_run_id_from_store(store), points=points)


@router.get("/top-listings", response_model=TopListingsResponse)
async def get_top_listings(
    limit: int = Query(10, ge=1, le=10),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> TopListingsResponse:
    """Топ-N SKU по GMV: price / gmv / volume per tick (dense backfill, §7.7)."""
    if store is None:
        return TopListingsResponse(run_id=_DEFAULT_RUN_ID, listings=[])

    df = store.top_listings_metrics(limit=limit)
    if df.height == 0:
        return TopListingsResponse(run_id=_run_id_from_store(store), listings=[])

    listings: list[ListingSeriesDTO] = []
    for listing_id in df[COL_LISTING_ID].unique().sort().to_list():
        part = df.filter(pl.col(COL_LISTING_ID) == listing_id)
        seller_id = int(part[COL_SELLER_ID][0])
        points = [
            ListingMetricPointDTO(
                tick_id=int(row[COL_TICK_ID]),
                price=row["price"],
                gmv=float(row["gmv"]),
                volume=int(row["volume"]),
            )
            for row in part.iter_rows(named=True)
        ]
        listings.append(
            ListingSeriesDTO(
                listing_id=int(listing_id),
                seller_id=seller_id,
                points=points,
            )
        )

    return TopListingsResponse(run_id=_run_id_from_store(store), listings=listings)


@router.get("/market-summary", response_model=MarketAggregateDTO)
async def get_market_summary(
    tick_id: int = Query(..., ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> MarketAggregateDTO:
    """Агрегаты одного тика (smoke / отладка)."""
    if store is None:
        return MarketAggregateDTO(
            mean_price=0.0,
            total_gmv=0.0,
            total_transactions=0,
            price_quantiles=None,
        )
    return _market_aggregate_from_store(store, tick_id)


@router.get("/system-events", response_model=SystemEventsResponse)
async def get_system_events(
    limit: int = Query(50, ge=1, le=200),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> SystemEventsResponse:
    """Cyber-log history: system_events sorted by tick_id desc."""
    if store is None:
        return SystemEventsResponse(events=[])

    rows = store.recent_system_events(limit=limit)
    events = [SystemEventDTO(**row) for row in rows]
    return SystemEventsResponse(events=events)


@router.get("/market-leaders", response_model=MarketLeadersResponse)
async def get_market_leaders(
    tick_id: int = Query(..., ge=0),
    limit: int = Query(5, ge=1, le=20),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> MarketLeadersResponse:
    """Top-N sellers by working_capital DESC (backend sort)."""
    if store is None:
        return MarketLeadersResponse(run_id=_DEFAULT_RUN_ID, tick_id=tick_id, leaders=[])

    raw = query_market_leaders(store, tick_id, limit=limit)
    leaders = [MarketLeaderRowDTO(**row) for row in raw["leaders"]]
    return MarketLeadersResponse(
        run_id=str(raw["run_id"]),
        tick_id=int(raw["tick_id"]),
        leaders=leaders,
    )


@router.get("/demand-matrix", response_model=DemandMatrixResponse)
async def get_demand_matrix(
    tick_id: int = Query(..., ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> DemandMatrixResponse:
    """10×10 demand density grid (v1 placeholder)."""
    if store is None:
        return DemandMatrixResponse(run_id=_DEFAULT_RUN_ID, tick_id=tick_id, cells=[])

    raw = query_demand_matrix(store, tick_id)
    cells = [DemandMatrixCellDTO(**cell) for cell in raw["cells"]]
    return DemandMatrixResponse(
        run_id=str(raw["run_id"]),
        tick_id=int(raw["tick_id"]),
        grid_size=int(raw["grid_size"]),
        cells=cells,
    )
