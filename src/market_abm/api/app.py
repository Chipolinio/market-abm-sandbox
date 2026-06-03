# Назначение файла: фабрика FastAPI-приложения (Slice 6.2).
# Базовая идея: create_app() принимает воркер как аргумент — чистая инжекция зависимостей,
# без глобального синглтона (тесты подменяют воркер напрямую).
from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from market_abm.api.routers.control import router as control_router


def create_app(*, worker: Any) -> FastAPI:
    """
    Фабрика приложения. Воркер инжектируется явно (не синглтон).
    Тесты передают мок, production — реальный SimulationWorker.
    """
    app = FastAPI(
        title="Market ABM Simulation API",
        description="REST API управления агентным симулятором рынка.",
        version="0.1.0",
    )
    app.state.worker = worker
    app.include_router(control_router)
    return app
