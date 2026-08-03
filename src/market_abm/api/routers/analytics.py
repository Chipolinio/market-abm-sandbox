# Назначение файла: REST read-only аналитика для UI backfill (Slice 7.1).
# Базовая идея: читает AnalyticsStore через app.state; CQRS query-side.
from __future__ import annotations

from typing import Any, Literal

import polars as pl
from fastapi import APIRouter, Depends, Query, Request

from market_abm.analytics.store import AnalyticsStore
from market_abm.api.schemas.analytics import (
    CategoryRankingResponse,
    CategoryRankingRowDTO,
    GmvByTickResponse,
    GmvPointDTO,
    ListingMetricPointDTO,
    ListingRankingBreakdownDTO,
    ListingSeriesDTO,
    PriceIndexPointDTO,
    PriceIndexResponse,
    SegmentHealthResponse,
    SegmentRowDTO,
    StrategyPulseResponse,
    StrategyPulseRowDTO,
    TopListingsResponse,
)
from market_abm.analytics.category_ranking import aggregate_category_ranking
from market_abm.analytics.leaders import query_demand_matrix, query_market_leaders
from market_abm.analytics.ranking_breakdown import compute_listing_ranking_breakdown
from market_abm.analytics.segments import aggregate_segment_health  # noqa: F401 — patch target 14.4-T4
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
    manifest = run_root / "manifest.json"
    events_dir = run_root / "system_events"
    has_parquet = any(run_root.glob("**/tick_*.parquet")) or (
        (events_dir / "events.parquet").is_file() or any(events_dir.glob("evt_*.parquet"))
    )
    if not manifest.is_file() and not has_parquet:
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
    limit: int = Query(200, ge=1, le=500),
    since_tick: int | None = Query(
        None,
        ge=-1,
        description="Incremental poll: events with tick_id >= since_tick (ASC).",
    ),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> SystemEventsResponse:
    """Cyber-log history: recent DESC by default; since_tick for live incremental poll."""
    if store is None:
        return SystemEventsResponse(events=[])

    if since_tick is not None:
        rows = store.system_events_since(since_tick, limit=limit)
    else:
        rows = store.recent_system_events(limit=limit)
    events = [SystemEventDTO(**row) for row in rows]
    return SystemEventsResponse(events=events)


@router.get("/market-leaders", response_model=MarketLeadersResponse)
async def get_market_leaders(
    tick_id: int = Query(..., ge=0),
    limit: int = Query(5, ge=1, le=1000),
    rank_by: Literal["working_capital", "tick_revenue", "cumulative_revenue"] = Query(
        "tick_revenue",
        description="Leader sort key (default tick_revenue for dynamic ranking).",
    ),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> MarketLeadersResponse:
    """Sellers ranked on backend; default rank_by=tick_revenue (Spec 011 §6.2)."""
    if store is None:
        return MarketLeadersResponse(run_id=_DEFAULT_RUN_ID, tick_id=tick_id, leaders=[])

    raw = query_market_leaders(store, tick_id, limit=limit, rank_by=rank_by)
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
    """Strategy × buyer-segment transaction heatmap."""
    if store is None:
        return DemandMatrixResponse(run_id=_DEFAULT_RUN_ID, tick_id=tick_id, cells=[])

    raw = query_demand_matrix(store, tick_id)
    cells = [DemandMatrixCellDTO(**cell) for cell in raw["cells"]]
    return DemandMatrixResponse(
        run_id=str(raw["run_id"]),
        tick_id=int(raw["tick_id"]),
        grid_size=int(raw["grid_size"]),
        row_count=int(raw["row_count"]),
        col_count=int(raw["col_count"]),
        x_labels=[str(label) for label in raw["x_labels"]],
        y_labels=[str(label) for label in raw["y_labels"]],
        axis_x=str(raw["axis_x"]),
        axis_y=str(raw["axis_y"]),
        cells=cells,
    )


def _segment_memory(request: Request) -> Any:
    return getattr(request.app.state, "segment_memory", None)


def _strategy_pulse_memory(request: Request) -> Any:
    return getattr(request.app.state, "strategy_pulse_memory", None)


def _worker_observability_snapshot(request: Request) -> Any:
    worker = getattr(request.app.state, "worker", None)
    reader = getattr(worker, "read_macro_snapshot", None) if worker is not None else None
    if callable(reader):
        snap = reader()
        if snap is not None and isinstance(getattr(snap, "macro_state", None), dict):
            return snap
    return None


@router.get("/segments", response_model=SegmentHealthResponse)
async def get_segments(
    request: Request,
    tick_id: int | None = Query(None, ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> SegmentHealthResponse:
    """O(1) read of precomputed segment health (Spec 014 §7.1)."""
    memory = _segment_memory(request)
    rows_raw: list[dict[str, object]] | None = None
    resolved_tick = tick_id if tick_id is not None else 0
    if memory is not None:
        rows_raw = memory.read(tick_id)
        if rows_raw is not None and tick_id is None:
            resolved_tick = int(getattr(memory, "_latest_tick", 0) or 0)
        elif tick_id is not None:
            resolved_tick = tick_id
    if rows_raw is None:
        snap = _worker_observability_snapshot(request)
        if snap is not None and isinstance(getattr(snap, "segments", None), list):
            rows_raw = list(snap.segments)
            resolved_tick = int(getattr(snap, "tick_id", resolved_tick))
    if rows_raw is None:
        return SegmentHealthResponse(
            run_id=_run_id_from_store(store),
            tick_id=resolved_tick,
            rows=[],
        )
    rows = [SegmentRowDTO.model_validate(row) for row in rows_raw]
    return SegmentHealthResponse(
        run_id=_run_id_from_store(store),
        tick_id=resolved_tick,
        rows=rows,
    )


@router.get("/strategy-pulse", response_model=StrategyPulseResponse)
async def get_strategy_pulse(
    request: Request,
    tick_id: int | None = Query(None, ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> StrategyPulseResponse:
    """Precomputed avg demand_index by strategy (Spec 014 §6.1)."""
    memory = _strategy_pulse_memory(request)
    payload: dict[str, object] | None = None
    resolved_tick = tick_id if tick_id is not None else 0
    if memory is not None:
        payload = memory.read(tick_id)
        if payload is not None:
            resolved_tick = int(payload.get("tick_id", resolved_tick))
    if payload is None:
        snap = _worker_observability_snapshot(request)
        if snap is not None and isinstance(getattr(snap, "strategy_pulse", None), dict):
            payload = dict(snap.strategy_pulse)
            resolved_tick = int(payload.get("tick_id", getattr(snap, "tick_id", resolved_tick)))
    if payload is None:
        return StrategyPulseResponse(
            run_id=_run_id_from_store(store),
            tick_id=resolved_tick,
            panic_active=False,
            strategies=[],
        )
    strategies = [
        StrategyPulseRowDTO.model_validate(row) for row in (payload.get("strategies") or [])
    ]
    return StrategyPulseResponse(
        run_id=_run_id_from_store(store),
        tick_id=resolved_tick,
        panic_active=bool(payload.get("panic_active", False)),
        strategies=strategies,
    )


@router.get("/listing-ranking", response_model=ListingRankingBreakdownDTO)
async def get_listing_ranking(
    request: Request,
    seller_id: int = Query(..., ge=0),
    tick_id: int = Query(0, ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> ListingRankingBreakdownDTO:
    """Ranking score breakdown for seller primary listing (Spec 014 §6.2)."""
    products = getattr(request.app.state, "ranking_products", None)
    if products is None and store is not None:
        try:
            products = store.products_snapshot_at_tick(tick_id)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            products = None
    if products is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="No products for ranking breakdown")
    breakdown = compute_listing_ranking_breakdown(products, seller_id=seller_id)
    if breakdown is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Seller listing not found")
    return ListingRankingBreakdownDTO.model_validate(breakdown)


def _products_for_category_ranking(
    request: Request,
    store: AnalyticsStore | None,
    tick_id: int,
) -> pl.DataFrame | None:
    """Prefer injected products; else full parquet snapshot (category/rating columns)."""
    products = getattr(request.app.state, "ranking_products", None)
    if products is not None:
        return products
    if store is None:
        return None
    path = store._run_root / "products_snapshots" / f"tick_{int(tick_id):06d}.parquet"
    if path.is_file():
        return pl.read_parquet(path)
    # Fallback: latest tick file if exact missing
    files = sorted((store._run_root / "products_snapshots").glob("tick_*.parquet"))
    if files:
        return pl.read_parquet(files[-1])
    return None


@router.get("/category-ranking", response_model=CategoryRankingResponse)
async def get_category_ranking(
    request: Request,
    tick_id: int = Query(0, ge=0),
    store: AnalyticsStore | None = Depends(_get_analytics_store),
) -> CategoryRankingResponse:
    """Per-category median score / price / sales (Spec 014 §7.2)."""
    products = _products_for_category_ranking(request, store, tick_id)
    if products is None or products.height == 0:
        return CategoryRankingResponse(
            run_id=_run_id_from_store(store),
            tick_id=tick_id,
            rows=[],
        )
    rows_raw = aggregate_category_ranking(products)
    rows = [CategoryRankingRowDTO.model_validate(row) for row in rows_raw]
    return CategoryRankingResponse(
        run_id=_run_id_from_store(store),
        tick_id=tick_id,
        rows=rows,
    )
