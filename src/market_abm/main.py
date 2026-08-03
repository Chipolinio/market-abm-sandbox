# Назначение файла: точка входа приложения (Slice 6.5 — E2E Integration).
# Базовая идея: configure_multiprocessing() → инициализация воркера и стора → create_app → uvicorn.
# Запуск (из корня репо, интерпретатор .venv):
#   ENABLE_CORS=1 .venv/bin/uvicorn market_abm.main:app --reload
# ENABLE_CORS=1 обязателен для vite dev (:5173). В Docker/Nginx CORS не нужен.
# Системный uvicorn без pip install -e . → ModuleNotFoundError: market_abm
from __future__ import annotations

import datetime
import multiprocessing as mp
import os
from collections.abc import Callable
from pathlib import Path

from market_abm.api.app import create_app
from market_abm.api.stub_telemetry import stub_tick_payload, zero_tick_payload
from market_abm.api.schemas.events import SystemEventDTO
from market_abm.api.schemas.stream import MarketAggregateDTO, PriceQuantilesDTO, TickStreamPayload
from market_abm.api.schemas.ticker import TickerMetricsDTO
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


def _completed_tick(next_tick: int) -> int:
    """tick_counter = next tick to run; Parquet/analytics keyed by last completed tick."""
    if next_tick <= 0:
        return 0
    return next_tick - 1


def make_payload_fn(store: object) -> Callable[[int], TickStreamPayload]:
    """
    Фабрика payload-функции для broadcaster_loop.
    Замыкает готовый store и возвращает callable tick_id → TickStreamPayload.
    """

    def _payload(next_tick: int) -> TickStreamPayload:
        if not (
            store._has_parquet_files("transactions")  # type: ignore[union-attr]
            or store._has_parquet_files("products_snapshots")
        ):
            return stub_tick_payload(next_tick)

        from market_abm.analytics.ticker import query_ticker_metrics
        from market_abm.api.schemas.macro import ActiveShockDTO, MacroStateDTO

        as_of_tick = _completed_tick(next_tick)
        agg: dict = store.query_market_aggregate(as_of_tick)  # type: ignore[union-attr]
        alerts: list[dict] = store.drift_alerts()  # type: ignore[union-attr]
        raw_q = agg.get("price_quantiles")
        quantiles: PriceQuantilesDTO | None = None
        if isinstance(raw_q, dict):
            quantiles = PriceQuantilesDTO(
                p10=float(raw_q["p10"]),
                p50=float(raw_q["p50"]),
                p90=float(raw_q["p90"]),
            )
        ticker_raw = query_ticker_metrics(store, as_of_tick)  # type: ignore[arg-type]
        ticker = TickerMetricsDTO(**{**ticker_raw, "current_tick": next_tick})
        try:
            raw_events = store.recent_system_events(limit=40)  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            raw_events = []
        frame_events = [SystemEventDTO(**event) for event in raw_events[:20]]

        macro_state = None
        active_shocks: list[ActiveShockDTO] = []
        ref_price: float | None = None
        memory = store.macro_memory() if hasattr(store, "macro_memory") else None  # type: ignore[union-attr]
        if memory is not None:
            snap = memory.read(as_of_tick)  # type: ignore[union-attr]
            if snap is None:
                snap = memory.read(None)  # type: ignore[union-attr]
            if snap is not None:
                macro_state = MacroStateDTO.model_validate(snap.macro_state)
                active_shocks = [
                    ActiveShockDTO.model_validate(row) for row in snap.active_shocks
                ]
                ref_price = snap.ref_price

        return TickStreamPayload(
            tick_id=next_tick,
            timestamp_utc=datetime.datetime.now(datetime.UTC).isoformat(),
            market_summary=MarketAggregateDTO(
                mean_price=float(agg["mean_price"]),
                total_gmv=float(agg["total_gmv"]),
                total_transactions=int(agg["total_transactions"]),
                price_quantiles=quantiles,
            ),
            ticker_metrics=ticker,
            active_drift_alerts=alerts,
            events=frame_events,
            macro_state=macro_state,
            active_shocks=active_shocks,
            ref_price=ref_price,
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
            return zero_tick_payload(tick_id)

        return make_payload_fn(_store)(tick_id)

    return _payload


configure_multiprocessing()

app = create_app(
    worker_factory=lambda: SimulationWorker(artifacts_dir=_ARTIFACTS_DIR),
    get_payload_fn=make_lazy_payload_fn(_ARTIFACTS_DIR),
    start_worker=True,
    artifacts_dir=_ARTIFACTS_DIR,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
