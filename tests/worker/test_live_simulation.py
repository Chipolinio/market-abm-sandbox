# Назначение файла: live worker session пишет Parquet (Slice 8.4).
from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import pytest

from market_abm.worker.process import WorkerCommand, WorkerState, _WorkerLoop
from market_abm.worker.simulation_session import make_live_step_fn
from tests.worker.test_simulation_worker import (
    _POLL_INTERVAL,
    _wait_for_state,
    _wait_for_tick_above,
)


def _wait_for_parquet(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return
        time.sleep(_POLL_INTERVAL)
    raise AssertionError(f"Timeout waiting for parquet: {path}")


def test_live_step_writes_transactions_parquet(tmp_path: Path) -> None:
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    tick_counter = __import__("multiprocessing").Value("i", 0)
    cmd_queue = __import__("multiprocessing").Queue(maxsize=1)
    state_value = __import__("multiprocessing").Value("i", WorkerState.IDLE.value)
    last_error_array = __import__("multiprocessing").Array("c", 2048)

    step_fn = make_live_step_fn(
        artifacts_dir=str(tmp_path),
        shock_queue=shock_queue,
        tick_counter=tick_counter,
    )
    loop = _WorkerLoop(
        command_queue=cmd_queue,
        tick_counter=tick_counter,
        state_value=state_value,
        last_error_array=last_error_array,
        artifacts_dir=str(tmp_path),
        step_fn=step_fn,
    )
    t = threading.Thread(target=loop.run, daemon=True)
    t.start()

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.RUNNING)
    _wait_for_tick_above(tick_counter, 0, timeout=30.0)

    parquet_path = tmp_path / "transactions" / "tick_000000.parquet"
    _wait_for_parquet(parquet_path)

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file()

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=5.0)


@pytest.mark.worker
def test_live_worker_process_writes_parquet(tmp_path: Path) -> None:
    from market_abm.worker.process import SimulationWorker

    worker = SimulationWorker(artifacts_dir=str(tmp_path))
    worker.process.start()
    try:
        worker.command_queue.put(WorkerCommand.START)
        _wait_for_tick_above(worker.tick_counter, 0, timeout=45.0)

        parquet_path = tmp_path / "transactions" / "tick_000000.parquet"
        _wait_for_parquet(parquet_path, timeout=45.0)
        assert worker.state != WorkerState.FAILED, worker.last_error
    finally:
        worker.command_queue.put(WorkerCommand.STOP)
        worker.process.join(timeout=10.0)
