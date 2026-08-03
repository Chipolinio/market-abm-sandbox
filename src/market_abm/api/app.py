# Назначение файла: фабрика FastAPI-приложения (Slice 6.2 / 6.3).
# Базовая идея: create_app() принимает воркер и опциональную payload-функцию как аргументы.
# Broadcaster запускается в lifespan и корректно останавливается при shutdown.
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from market_abm.api.broadcaster import ConnectionManager, broadcaster_loop
from market_abm.api.routers.analytics import router as analytics_router
from market_abm.api.routers.control import router as control_router
from market_abm.api.routers.experiments import router as experiments_router
from market_abm.api.routers.health import router as health_router
from market_abm.api.routers.stream import router as stream_router
from market_abm.api.schemas.stream import TickStreamPayload
from market_abm.api.stub_telemetry import stub_tick_payload
from market_abm.worker.process import WorkerState, shutdown_simulation_worker

_DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins_from_env() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(_DEFAULT_CORS_ORIGINS)


def _maybe_add_cors(app: FastAPI, *, enable: bool) -> None:
    """Dev-only CORS для vite :5173 → api :8000 (Spec 007 §7.6)."""
    if not enable:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins_from_env(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _shutdown_worker(worker: Any) -> None:
    """
    Штатный шатдаун воркера (Spec 006 §3.5).
    Делегирует в shutdown_simulation_worker; для моков без shock_queue — duck-typing.
    """
    try:
        shutdown_simulation_worker(worker)
    except Exception:
        pass


def _wrap_payload_with_worker_state(
    base_fn: Callable[[int], TickStreamPayload],
    worker: Any,
) -> Callable[[int], TickStreamPayload]:
    """Добавляет worker_state и macro IPC snapshot в каждый WS-кадр (Spec 007 / 014)."""

    def _payload(tick_id: int) -> TickStreamPayload:
        payload = base_fn(tick_id)
        state: WorkerState = worker.state
        updates: dict[str, object] = {"worker_state": state.name}

        reader = getattr(worker, "read_macro_snapshot", None)
        snap = reader() if callable(reader) else None
        macro_state = getattr(snap, "macro_state", None) if snap is not None else None
        if isinstance(macro_state, dict):
            from market_abm.api.schemas.macro import ActiveShockDTO, MacroStateDTO

            updates["macro_state"] = MacroStateDTO.model_validate(macro_state)
            raw_shocks = getattr(snap, "active_shocks", None) or []
            if isinstance(raw_shocks, list):
                updates["active_shocks"] = [
                    ActiveShockDTO.model_validate(row)
                    for row in raw_shocks
                    if isinstance(row, dict)
                ]
            ref = getattr(snap, "ref_price", None)
            updates["ref_price"] = float(ref) if isinstance(ref, (int, float)) else None

        return payload.model_copy(update=updates)

    return _payload


def _default_payload_fn(tick_id: int) -> TickStreamPayload:
    """Stub-телеметрия до появления Parquet (заменяется DuckDB при реальной симуляции)."""
    return stub_tick_payload(tick_id)


def create_app(
    *,
    worker: Any = None,
    worker_factory: Callable[[], Any] | None = None,
    get_payload_fn: Callable[[int], TickStreamPayload] | None = None,
    start_worker: bool = False,
    artifacts_dir: str | None = None,
    analytics_store: Any = None,
    experiments_dir: str | None = None,
    enable_cors: bool | None = None,
) -> FastAPI:
    """
    Фабрика приложения.
    - worker: SimulationWorker (или мок) — передаётся напрямую (для тестов)
    - worker_factory: callable () → worker — создаётся внутри lifespan (для prod/--reload)
      Устраняет утечку POSIX-семафоров при uvicorn --reload: IPC-примитивы живут
      ровно в рамках одного lifespan-цикла и корректно освобождаются при shutdown.
    - get_payload_fn: функция tick_id → TickStreamPayload (None → stub)
    - start_worker: если True, lifespan вызывает worker.process.start() при старте
    - artifacts_dir: корень Parquet-артефактов для analytics router (prod)
    - analytics_store: инжектированный AnalyticsStore (тесты)
    - experiments_dir: корень batch experiment outputs (Spec 015 Research Lab)
    - enable_cors: True при ENABLE_CORS=1 (vite dev); в Docker/Nginx — False
    """
    if enable_cors is None:
        enable_cors = os.getenv("ENABLE_CORS", "0") == "1"

    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        w = worker_factory() if worker_factory is not None else worker
        base_payload_fn = get_payload_fn or _default_payload_fn
        payload_fn = _wrap_payload_with_worker_state(base_payload_fn, w)
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
    _maybe_add_cors(app, enable=enable_cors)
    if worker is not None:
        app.state.worker = worker
    app.state.ws_manager = ws_manager
    app.state.artifacts_dir = artifacts_dir
    app.state.analytics_store = analytics_store
    app.state.experiments_dir = experiments_dir or os.getenv(
        "EXPERIMENTS_DIR", "output/experiments"
    )
    app.include_router(health_router)
    app.include_router(control_router)
    app.include_router(analytics_router)
    app.include_router(experiments_router)
    app.include_router(stream_router)
    return app
