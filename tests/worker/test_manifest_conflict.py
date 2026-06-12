# Slice A.2 — merge analytics manifest + worker status on FAILED (TD-MANIFEST).
from __future__ import annotations

import json
import queue
from pathlib import Path

from market_abm.worker.process import WorkerCommand, WorkerState
from market_abm.worker.simulation_session import LiveSimulationSession
from tests.worker.test_simulation_worker import (
    _make_loop,
    _run_loop_in_thread,
    _wait_for_state,
)


def _write_analytics_manifest(run_root: Path, **overrides: object) -> dict[str, object]:
    """Имитирует manifest после LiveSimulationSession / persist_tick_artifacts."""
    payload: dict[str, object] = {
        "run_id": "test-run",
        "created_at_utc": "2026-06-12T00:00:00Z",
        "n_ticks": 1_000_000,
        "seed": 42,
        "n_buyers": 100,
        "n_sellers": 30,
        "n_listings": 30,
        "config_hash": "deadbeef",
        "engine": "numpy_softmax",
        "ticks_completed": 5,
        "last_tick_id": 4,
        "paths": {
            "transactions_glob": "transactions/tick_*.parquet",
            "products_glob": "products_snapshots/tick_*.parquet",
        },
    }
    payload.update(overrides)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def _read_manifest(run_root: Path) -> dict[str, object]:
    return json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A.2 — worker FAILED must merge, not clobber analytics manifest
# ---------------------------------------------------------------------------


def test_a2_t1_failed_preserves_analytics_manifest_fields(tmp_path: Path) -> None:
    _write_analytics_manifest(tmp_path, n_buyers=250, ticks_completed=12, last_tick_id=11)

    def _raising_step() -> None:
        raise RuntimeError("disk full")

    loop, cmd_queue, _, state_value, _ = _make_loop(step_fn=_raising_step, tmp_path=tmp_path)
    t = _run_loop_in_thread(loop)

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.FAILED)

    manifest = _read_manifest(tmp_path)
    assert manifest["n_buyers"] == 250
    assert manifest["ticks_completed"] == 12
    assert manifest["last_tick_id"] == 11
    assert manifest["run_id"] == "test-run"
    assert manifest["config_hash"] == "deadbeef"

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=3.0)


def test_a2_t2_failed_merges_worker_state_and_last_error(tmp_path: Path) -> None:
    error_msg = "OOM: not enough memory"
    _write_analytics_manifest(tmp_path)

    def _raising_step() -> None:
        raise RuntimeError(error_msg)

    loop, cmd_queue, _, state_value, _ = _make_loop(step_fn=_raising_step, tmp_path=tmp_path)
    t = _run_loop_in_thread(loop)

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.FAILED)

    manifest = _read_manifest(tmp_path)
    assert manifest["state"] == "FAILED"
    assert error_msg in str(manifest["last_error"])
    assert manifest["n_buyers"] == 100
    assert manifest["ticks_completed"] == 5

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=3.0)


def test_a2_t3_live_tick_then_failed_retains_population_stats(tmp_path: Path) -> None:
    """1 успешный live-тик → analytics manifest → FAIL на следующем step."""
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)
    session.run_tick(0)

    assert (tmp_path / "manifest.json").is_file()
    before_fail = _read_manifest(tmp_path)
    assert before_fail["n_buyers"] == 300  # worker default without pending overlay
    assert before_fail.get("ticks_completed", 0) >= 1

    def _fail_on_next_step() -> None:
        raise RuntimeError("simulation exploded on tick 2")

    loop, cmd_queue, _, state_value, _ = _make_loop(step_fn=_fail_on_next_step, tmp_path=tmp_path)
    t = _run_loop_in_thread(loop)

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.FAILED, timeout=10.0)

    after_fail = _read_manifest(tmp_path)
    assert after_fail["state"] == "FAILED"
    assert "simulation exploded" in str(after_fail["last_error"])
    assert after_fail["n_buyers"] == before_fail["n_buyers"]
    assert after_fail["ticks_completed"] == before_fail["ticks_completed"]
    assert after_fail["last_tick_id"] == before_fail["last_tick_id"]

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=5.0)


def test_a2_t4_failed_without_prior_analytics_writes_worker_only_manifest(tmp_path: Path) -> None:
    """Нет analytics manifest → только worker overlay (backward compat)."""

    def _raising_step() -> None:
        raise RuntimeError("early boot failure")

    loop, cmd_queue, _, state_value, _ = _make_loop(step_fn=_raising_step, tmp_path=tmp_path)
    t = _run_loop_in_thread(loop)

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.FAILED)

    manifest = _read_manifest(tmp_path)
    assert manifest["state"] == "FAILED"
    assert "early boot failure" in str(manifest["last_error"])
    assert "n_buyers" not in manifest

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=3.0)


def test_a2_t5_failed_manifest_no_tmp_file_left(tmp_path: Path) -> None:
    _write_analytics_manifest(tmp_path)

    loop, cmd_queue, _, state_value, _ = _make_loop(
        step_fn=lambda: (_ for _ in ()).throw(RuntimeError("err")),
        tmp_path=tmp_path,
    )
    t = _run_loop_in_thread(loop)

    cmd_queue.put(WorkerCommand.START)
    _wait_for_state(state_value, WorkerState.FAILED)

    assert not (tmp_path / "manifest.json.tmp").exists()

    cmd_queue.put(WorkerCommand.STOP)
    t.join(timeout=3.0)
