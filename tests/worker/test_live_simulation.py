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


def test_run_tick_can_restart_at_tick_zero(tmp_path: Path) -> None:
    """RESET → START с tick=0 не должен падать на существующем tick_000000.parquet."""
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = __import__(
        "market_abm.worker.simulation_session", fromlist=["LiveSimulationSession"]
    ).LiveSimulationSession(tmp_path, shock_queue)

    session.run_tick(0)
    assert (tmp_path / "transactions" / "tick_000000.parquet").is_file()

    session.run_tick(0)
    assert (tmp_path / "transactions" / "tick_000000.parquet").is_file()


def test_reset_clears_parquet_and_allows_rerun(tmp_path: Path) -> None:
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
    _wait_for_parquet(tmp_path / "transactions" / "tick_000000.parquet")

    cmd_queue.put(WorkerCommand.RESET)
    _wait_for_state(state_value, WorkerState.IDLE)
    assert not (tmp_path / "transactions" / "tick_000000.parquet").exists()

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.RUNNING)
    _wait_for_tick_above(tick_counter, 0, timeout=30.0)
    _wait_for_parquet(tmp_path / "transactions" / "tick_000000.parquet")
    assert WorkerState(state_value.value) != WorkerState.FAILED

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=5.0)


def test_pause_start_does_not_fail_when_tick_zero_on_disk(tmp_path: Path) -> None:
    """PAUSE → START: tick=0 уже на диске, counter=0 — idempotent skip, не FileExistsError."""
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
    _wait_for_parquet(tmp_path / "transactions" / "tick_000000.parquet", timeout=30.0)

    cmd_queue.put(WorkerCommand.PAUSE)
    _wait_for_state(state_value, WorkerState.PAUSED)

    with tick_counter.get_lock():
        tick_counter.value = 0

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.RUNNING)
    time.sleep(0.5)
    assert WorkerState(state_value.value) != WorkerState.FAILED, (
        last_error_array.raw.rstrip(b"\x00").decode("utf-8")
    )

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
