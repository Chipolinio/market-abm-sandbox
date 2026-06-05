# Demo-телеметрия для noop/stub воркера до подключения реальной симуляции (Spec 007).
from __future__ import annotations

import datetime
import math

from market_abm.api.schemas.stream import MarketAggregateDTO, PriceQuantilesDTO, TickStreamPayload


def stub_market_summary(tick_id: int) -> MarketAggregateDTO:
    """Синтетические, но правдоподобные метрики — чтобы UI был живым без Parquet."""
    mean = 100.0 + 8.0 * math.sin(tick_id / 30.0)
    spread = 5.0 + 2.0 * math.cos(tick_id / 45.0)
    p50 = mean
    p10 = mean - spread
    p90 = mean + spread
    gmv = max(0.0, 50.0 + 30.0 * math.sin(tick_id / 20.0))
    txns = max(0, int(5 + 3 * math.sin(tick_id / 15.0)))
    return MarketAggregateDTO(
        mean_price=round(mean, 4),
        total_gmv=round(gmv, 2),
        total_transactions=txns,
        price_quantiles=PriceQuantilesDTO(
            p10=round(p10, 4),
            p50=round(p50, 4),
            p90=round(p90, 4),
        ),
    )


def zero_tick_payload(tick_id: int) -> TickStreamPayload:
    """Нулевые агрегаты до появления manifest.json (Spec 007 §4.1)."""
    return TickStreamPayload(
        tick_id=tick_id,
        timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        market_summary=MarketAggregateDTO(
            mean_price=0.0,
            total_gmv=0.0,
            total_transactions=0,
            price_quantiles=None,
        ),
        active_drift_alerts=[],
    )


def stub_tick_payload(tick_id: int) -> TickStreamPayload:
    return TickStreamPayload(
        tick_id=tick_id,
        timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        market_summary=stub_market_summary(tick_id),
        active_drift_alerts=[],
    )
