# Назначение файла: фабрика FastAPI-приложения (Slice 6.2 / 6.3).
# Базовая идея: create_app() принимает воркер и опциональную payload-функцию как аргументы.
# Broadcaster запускается в lifespan и корректно останавливается при shutdown.
from __future__ import annotations

import asyncio
import datetime
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from market_abm.api.broadcaster import ConnectionManager, broadcaster_loop
from market_abm.api.routers.control import router as control_router
from market_abm.api.routers.stream import router as stream_router
from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload


def _default_payload_fn(tick_id: int) -> TickStreamPayload:
    """Stub-функция для получения фрейма телеметрии (заменяется в Slice 6.4 на DuckDB)."""
    return TickStreamPayload(
        tick_id=tick_id,
        timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        market_summary=MarketAggregateDTO(
            mean_price=0.0,
            total_gmv=0.0,
            total_transactions=0,
        ),
        active_drift_alerts=[],
    )


def create_app(
    *,
    worker: Any,
    get_payload_fn: Callable[[int], TickStreamPayload] | None = None,
) -> FastAPI:
    """
    Фабрика приложения.
    - worker: SimulationWorker (или мок) — инжектируется без синглтона
    - get_payload_fn: функция tick_id → TickStreamPayload (None → stub)
    """
    payload_fn = get_payload_fn or _default_payload_fn
    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        task = asyncio.create_task(
            broadcaster_loop(ws_manager, worker.tick_counter, payload_fn)
        )
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    app = FastAPI(
        title="Market ABM Simulation API",
        description="REST API управления агентным симулятором рынка.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    app.state.worker = worker
    app.state.ws_manager = ws_manager
    app.include_router(control_router)
    app.include_router(stream_router)
    return app
