# Тесты REST Control API (Slice 6.2).
# Стратегия: FastAPI TestClient с мок-воркером (SimulationWorker подменяется фикстурой).
# asyncio.to_thread тестируется через инжектирование реального Queue (sync → async bridge).
from __future__ import annotations

import multiprocessing as mp
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from market_abm.api.schemas import SimulationStartRequest, SimulationStatusResponse
from market_abm.api.app import create_app
from market_abm.worker.process import WorkerCommand, WorkerState


def _make_mock_worker(
    state: WorkerState = WorkerState.IDLE,
    tick: int = 0,
    last_error: str | None = None,
) -> MagicMock:
    """
    Лёгкий мок SimulationWorker для тестов Control API.
    Использует реальный mp.Queue(maxsize=1) — тесты проверяют реальный IPC-контракт.
    """
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.tick_counter = mp.Value("i", tick)
    worker.state = state
    worker.last_error = last_error
    worker.run_id = "test-run"
    worker._artifacts_dir = tempfile.mkdtemp(prefix="test-run-")
    return worker


def _make_client(worker: MagicMock) -> TestClient:
    """Создаёт TestClient с подменённым воркером через dependency override."""
    app = create_app(worker=worker)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def idle_worker() -> MagicMock:
    return _make_mock_worker(WorkerState.IDLE)


@pytest.fixture()
def running_worker() -> MagicMock:
    return _make_mock_worker(WorkerState.RUNNING, tick=42)


@pytest.fixture()
def paused_worker() -> MagicMock:
    return _make_mock_worker(WorkerState.PAUSED, tick=10)


@pytest.fixture()
def stopped_worker() -> MagicMock:
    return _make_mock_worker(WorkerState.STOPPED, tick=100)


@pytest.fixture()
def failed_worker() -> MagicMock:
    return _make_mock_worker(WorkerState.FAILED, tick=5, last_error="OOM: boom")


def test_simulation_start_request_defaults() -> None:
    req = SimulationStartRequest()
    assert req.n_buyers == 1000
    assert req.n_sellers == 50
    assert req.repricing_mode == "rules"
    assert req.force_clear is False
    assert req.run_id is None


def test_simulation_start_request_validation_n_buyers_limit() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SimulationStartRequest(n_buyers=200_000)


def test_simulation_start_request_validation_repricing_mode() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SimulationStartRequest(repricing_mode="unknown_mode")


def test_simulation_status_response_all_states_valid() -> None:
    for state in ("IDLE", "RUNNING", "PAUSED", "STOPPED", "FAILED"):
        resp = SimulationStatusResponse(
            run_id="test-run",
            state=state,
            current_tick=0,
            elapsed_time_seconds=0.0,
        )
        assert resp.state == state


def test_simulation_status_response_invalid_state() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        SimulationStatusResponse(
            run_id="x",
            state="UNKNOWN",
            current_tick=0,
            elapsed_time_seconds=0.0,
        )


def test_start_from_idle_returns_202(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.post("/api/v1/simulation/start")
    assert resp.status_code == 202


def test_start_enqueues_start_command(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    client.post("/api/v1/simulation/start")
    cmd = idle_worker.command_queue.get_nowait()
    assert cmd == WorkerCommand.START


def test_start_from_running_returns_400(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.post("/api/v1/simulation/start")
    assert resp.status_code == 400
    assert "already running" in resp.json()["detail"].lower()


def test_start_from_stopped_without_force_clear_returns_400(stopped_worker: MagicMock) -> None:
    client = _make_client(stopped_worker)
    resp = client.post("/api/v1/simulation/start", json={"force_clear": False})
    assert resp.status_code == 400
    assert "force_clear" in resp.json()["detail"].lower()


def test_start_from_stopped_with_force_clear_returns_202(stopped_worker: MagicMock) -> None:
    client = _make_client(stopped_worker)
    resp = client.post("/api/v1/simulation/start", json={"force_clear": True})
    assert resp.status_code == 202


def test_start_from_failed_with_force_clear_returns_202(failed_worker: MagicMock) -> None:
    client = _make_client(failed_worker)
    resp = client.post("/api/v1/simulation/start", json={"force_clear": True})
    assert resp.status_code == 202


def test_start_queue_full_returns_429(idle_worker: MagicMock) -> None:
    idle_worker.command_queue.put_nowait(WorkerCommand.PAUSE)
    client = _make_client(idle_worker)
    resp = client.post("/api/v1/simulation/start")
    assert resp.status_code == 429


def test_start_response_body_contains_state(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.post("/api/v1/simulation/start")
    body = resp.json()
    assert "state" in body or "message" in body


def test_pause_from_running_returns_202(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.post("/api/v1/simulation/pause")
    assert resp.status_code == 202


def test_pause_enqueues_pause_command(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    client.post("/api/v1/simulation/pause")
    cmd = running_worker.command_queue.get_nowait()
    assert cmd == WorkerCommand.PAUSE


def test_pause_from_idle_returns_400(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.post("/api/v1/simulation/pause")
    assert resp.status_code == 400


def test_pause_queue_full_returns_429(running_worker: MagicMock) -> None:
    running_worker.command_queue.put_nowait(WorkerCommand.START)
    client = _make_client(running_worker)
    resp = client.post("/api/v1/simulation/pause")
    assert resp.status_code == 429


def test_step_from_paused_returns_202(paused_worker: MagicMock) -> None:
    client = _make_client(paused_worker)
    resp = client.post("/api/v1/simulation/step")
    assert resp.status_code == 202


def test_step_enqueues_step_command(paused_worker: MagicMock) -> None:
    client = _make_client(paused_worker)
    client.post("/api/v1/simulation/step")
    cmd = paused_worker.command_queue.get_nowait()
    assert cmd == WorkerCommand.STEP


def test_step_from_running_returns_400(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.post("/api/v1/simulation/step")
    assert resp.status_code == 400
    assert "pause first" in resp.json()["detail"].lower()


def test_step_from_idle_returns_400(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.post("/api/v1/simulation/step")
    assert resp.status_code == 400


def test_step_queue_full_returns_429(paused_worker: MagicMock) -> None:
    paused_worker.command_queue.put_nowait(WorkerCommand.START)
    client = _make_client(paused_worker)
    resp = client.post("/api/v1/simulation/step")
    assert resp.status_code == 429


def test_reset_from_stopped_returns_202(stopped_worker: MagicMock) -> None:
    client = _make_client(stopped_worker)
    resp = client.post("/api/v1/simulation/reset")
    assert resp.status_code == 202


def test_reset_from_failed_returns_202(failed_worker: MagicMock) -> None:
    client = _make_client(failed_worker)
    resp = client.post("/api/v1/simulation/reset")
    assert resp.status_code == 202


def test_reset_from_running_returns_400(running_worker: MagicMock) -> None:
    """RESET во время RUNNING — опасная операция, запрещена."""
    client = _make_client(running_worker)
    resp = client.post("/api/v1/simulation/reset")
    assert resp.status_code == 400


def test_reset_queue_full_returns_429(stopped_worker: MagicMock) -> None:
    stopped_worker.command_queue.put_nowait(WorkerCommand.STOP)
    client = _make_client(stopped_worker)
    resp = client.post("/api/v1/simulation/reset")
    assert resp.status_code == 429


def test_status_returns_200(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.get("/api/v1/simulation/status")
    assert resp.status_code == 200


def test_status_response_schema(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.get("/api/v1/simulation/status")
    body = resp.json()
    assert "state" in body
    assert "current_tick" in body
    assert "elapsed_time_seconds" in body
    assert "run_id" in body


def test_status_reflects_worker_state(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.get("/api/v1/simulation/status")
    assert resp.json()["state"] == "RUNNING"


def test_status_reflects_tick_counter(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.get("/api/v1/simulation/status")
    assert resp.json()["current_tick"] == 42


def test_status_returns_last_error_when_failed(failed_worker: MagicMock) -> None:
    client = _make_client(failed_worker)
    resp = client.get("/api/v1/simulation/status")
    body = resp.json()
    assert body["state"] == "FAILED"
    assert body["last_error"] == "OOM: boom"


def test_status_last_error_none_when_healthy(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.get("/api/v1/simulation/status")
    assert resp.json()["last_error"] is None


def test_status_validates_response_schema_via_pydantic(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.get("/api/v1/simulation/status")
    parsed = SimulationStatusResponse.model_validate(resp.json())
    assert parsed.state == "IDLE"


def test_configure_accepts_session_when_idle(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.post(
        "/api/v1/simulation/configure",
        json={
            "n_buyers": 5000,
            "seller_mix": {
                "catboost_pct": 0.4,
                "rule_based_pct": 0.35,
                "basic_pct": 0.25,
            },
        },
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "accepted"
    assert resp.json()["n_buyers"] == 5000

    pending_path = Path(idle_worker._artifacts_dir) / "pending_session.json"
    assert pending_path.is_file()


def test_get_configure_returns_defaults_when_no_pending(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    resp = client.get("/api/v1/simulation/configure")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_buyers"] == 10_000
    assert body["seller_mix"]["catboost_pct"] == pytest.approx(0.4)


def test_get_configure_returns_pending_session(idle_worker: MagicMock) -> None:
    client = _make_client(idle_worker)
    client.post(
        "/api/v1/simulation/configure",
        json={
            "n_buyers": 5000,
            "seller_mix": {
                "catboost_pct": 0.4,
                "rule_based_pct": 0.35,
                "basic_pct": 0.25,
            },
        },
    )
    resp = client.get("/api/v1/simulation/configure")
    assert resp.status_code == 200
    assert resp.json()["n_buyers"] == 5000


def test_configure_rejects_when_running(running_worker: MagicMock) -> None:
    client = _make_client(running_worker)
    resp = client.post(
        "/api/v1/simulation/configure",
        json={
            "n_buyers": 5000,
            "seller_mix": {
                "catboost_pct": 0.4,
                "rule_based_pct": 0.35,
                "basic_pct": 0.25,
            },
        },
    )
    assert resp.status_code == 400
