# Назначение файла: точка входа приложения (Slice 6.5 — E2E Integration).
# Базовая идея: configure_multiprocessing() → инициализация воркера и стора → create_app → uvicorn.
# Запуск: uvicorn market_abm.main:app --reload
from __future__ import annotations

import datetime
import multiprocessing as mp
import os
from collections.abc import Callable
from pathlib import Path

from market_abm.api.app import _default_payload_fn, create_app
from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.worker.process import SimulationWorker

__all__ = [
    "app",
    "configure_multiprocessing",
    "make_payload_fn",
    "make_lazy_payload_fn",
]

_ARTIFACTS_DIR: str = os.getenv("SIMULATION_ARTIFACTS_DIR", "runs/default")


def configure_multiprocessing() -> None:
    """
    Задаёт метод старта процессов 'spawn' до инициализации FastAPI.
    Обязателен на Linux/macOS: 'fork' копирует заблокированные пулы DuckDB/Uvicorn → Deadlock.
    """
    mp.set_start_method("spawn", force=True)


def make_payload_fn(store: object) -> Callable[[int], TickStreamPayload]:
    """
    Фабрика payload-функции для broadcaster_loop.
    Замыкает готовый store и возвращает callable tick_id → TickStreamPayload.
    """

    def _payload(tick_id: int) -> TickStreamPayload:
        agg: dict = store.query_market_aggregate(tick_id)  # type: ignore[union-attr]
        alerts: list[dict] = store.drift_alerts()  # type: ignore[union-attr]
        return TickStreamPayload(
            tick_id=tick_id,
            timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
            market_summary=MarketAggregateDTO(
                mean_price=float(agg["mean_price"]),
                total_gmv=float(agg["total_gmv"]),
                total_transactions=int(agg["total_transactions"]),
            ),
            active_drift_alerts=alerts,
        )

    return _payload


def make_lazy_payload_fn(artifacts_dir: str) -> Callable[[int], TickStreamPayload]:
    """
    Payload-функция с ленивой инициализацией AnalyticsStore.
    AnalyticsStore открывается при первом тике после появления manifest.json.
    До тех пор возвращает нулевые агрегаты — не бросает FileNotFoundError при старте.
    """
    _store: object | None = None

    def _payload(tick_id: int) -> TickStreamPayload:
        nonlocal _store
        if _store is None:
            manifest = Path(artifacts_dir) / "manifest.json"
            if manifest.is_file():
                from market_abm.analytics.store import AnalyticsStore

                _store = AnalyticsStore(run_root=artifacts_dir)

        if _store is None:
            return _default_payload_fn(tick_id)

        return make_payload_fn(_store)(tick_id)

    return _payload


configure_multiprocessing()

app = create_app(
    worker_factory=lambda: SimulationWorker(artifacts_dir=_ARTIFACTS_DIR),
    get_payload_fn=make_lazy_payload_fn(_ARTIFACTS_DIR),
    start_worker=True,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
