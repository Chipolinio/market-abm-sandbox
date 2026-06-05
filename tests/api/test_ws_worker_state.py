# WS payload должен содержать актуальный worker_state (Spec 007 §4.1).
from __future__ import annotations

import multiprocessing as mp
from unittest.mock import MagicMock

from market_abm.api.app import _wrap_payload_with_worker_state
from market_abm.api.schemas.stream import MarketAggregateDTO, TickStreamPayload
from market_abm.worker.process import WorkerState


def _make_mock_worker(state: WorkerState = WorkerState.RUNNING) -> MagicMock:
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.tick_counter = mp.Value("i", 42)
    worker.state = state
    worker.last_error = None
    worker.run_id = "ws-state-test"
    return worker


def test_wrap_payload_injects_worker_state() -> None:
    worker = _make_mock_worker(WorkerState.PAUSED)

    def _base(_tick_id: int) -> TickStreamPayload:
        return TickStreamPayload(
            tick_id=1,
            timestamp_utc="2026-06-05T12:00:00Z",
            market_summary=MarketAggregateDTO(
                mean_price=0.0,
                total_gmv=0.0,
                total_transactions=0,
            ),
            active_drift_alerts=[],
        )

    payload = _wrap_payload_with_worker_state(_base, worker)(7)
    assert payload.worker_state == "PAUSED"
    assert payload.tick_id == 1


def test_wrap_payload_reads_live_worker_state() -> None:
    worker = _make_mock_worker(WorkerState.RUNNING)

    def _capture_fn(tick_id: int) -> TickStreamPayload:
        from market_abm.api.app import _default_payload_fn

        return _default_payload_fn(tick_id)

    worker.state = WorkerState.IDLE
    fn = _wrap_payload_with_worker_state(_capture_fn, worker)
    assert fn(0).worker_state == "IDLE"

    worker.state = WorkerState.RUNNING
    assert fn(1).worker_state == "RUNNING"
