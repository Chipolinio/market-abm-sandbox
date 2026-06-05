# Назначение файла: REST read-only аналитика для UI backfill (Slice 7.1).
# Базовая идея: читает AnalyticsStore через app.state; CQRS query-side.
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from market_abm.analytics.store import AnalyticsStore
from market_abm.api.schemas.analytics import (
    GmvByTickResponse,
    GmvPointDTO,
    PriceIndexPointDTO,
    PriceIndexResponse,
)
from market_abm.api.schemas.stream import MarketAggregateDTO, PriceQuantilesDTO
from market_abm.domain.constants import COL_TICK_ID

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
