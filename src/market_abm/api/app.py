# Назначение файла: фабрика FastAPI-приложения (Slice 6.2 / 6.3).
# Базовая идея: create_app() принимает воркер и опциональную payload-функцию как аргументы.
# Broadcaster запускается в lifespan и корректно останавливается при shutdown.
from __future__ import annotations

import asyncio
import datetime
import queue
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from market_abm.api.broadcaster import ConnectionManager, broadcaster_loop
from market_abm.api.routers.control import router as control_router
from market_abm.api.routers.stream import router as stream_router
from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.worker.process import WorkerCommand


def _shutdown_worker(worker: Any) -> None:
    """
    Штатный шатдаун воркера (Spec 006 §3.5).
    Порядок: STOP → join(5s) → queue.close() / join_thread().
    Все шаги защищены от исключений — не блокируют остановку FastAPI.
    """
    try:
        worker.command_queue.put_nowait(WorkerCommand.STOP)
    except queue.Full:
        pass
    except Exception:
        pass

    try:
        worker.process.join(timeout=5.0)
    except Exception:
        pass

    try:
        worker.command_queue.close()
    except Exception:
        pass

    try:
        worker.command_queue.join_thread()
    except Exception:
        pass


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
    worker: Any = None,
    worker_factory: Callable[[], Any] | None = None,
    get_payload_fn: Callable[[int], TickStreamPayload] | None = None,
    start_worker: bool = False,
) -> FastAPI:
    """
    Фабрика приложения.
    - worker: SimulationWorker (или мок) — передаётся напрямую (для тестов)
    - worker_factory: callable () → worker — создаётся внутри lifespan (для prod/--reload)
      Устраняет утечку POSIX-семафоров при uvicorn --reload: IPC-примитивы живут
      ровно в рамках одного lifespan-цикла и корректно освобождаются при shutdown.
    - get_payload_fn: функция tick_id → TickStreamPayload (None → stub)
    - start_worker: если True, lifespan вызывает worker.process.start() при старте
    """
    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        w = worker_factory() if worker_factory is not None else worker
        payload_fn = get_payload_fn or _default_payload_fn
        app.state.worker = w
        if start_worker:
            w.process.start()
        task = asyncio.create_task(
            broadcaster_loop(ws_manager, w.tick_counter, payload_fn)
        )
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            _shutdown_worker(w)

    app = FastAPI(
        title="Market ABM Simulation API",
        description="REST API управления агентным симулятором рынка.",
        version="0.1.0",
        lifespan=_lifespan,
    )
    if worker is not None:
        app.state.worker = worker
    app.state.ws_manager = ws_manager
    app.include_router(control_router)
    app.include_router(stream_router)
    return app
