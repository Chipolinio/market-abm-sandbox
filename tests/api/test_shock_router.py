# Назначение файла: REST POST /api/v1/simulation/shock (Slice 8.1).
from __future__ import annotations

import multiprocessing as mp
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from market_abm.api.app import create_app
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand
from market_abm.worker.process import WorkerState


def _make_mock_worker(state: WorkerState = WorkerState.IDLE) -> MagicMock:
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.shock_queue = mp.Queue(maxsize=32)
    worker.tick_counter = mp.Value("i", 0)
    worker.state = state
    worker.last_error = None
    worker.run_id = "test-run"
    return worker


def test_post_shock_returns_202() -> None:
    worker = _make_mock_worker()
    client = TestClient(create_app(worker=worker), raise_server_exceptions=True)

    resp = client.post(
        "/api/v1/simulation/shock",
        json={
            "shock_type": "demand_crash",
            "intensity": 1.0,
            "duration_ticks": 10,
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["shock_type"] == "demand_crash"
    assert body["queue_depth"] >= 1

    cmd = worker.shock_queue.get_nowait()
    assert cmd == ShockCommand(ShockType.DEMAND_CRASH, 1.0, 10)


def test_post_shock_queue_full_429() -> None:
    worker = _make_mock_worker()
    for _ in range(32):
        worker.shock_queue.put_nowait(
            ShockCommand(ShockType.DEMAND_CRASH, 1.0, 10)
        )

    client = TestClient(create_app(worker=worker), raise_server_exceptions=True)
    resp = client.post(
        "/api/v1/simulation/shock",
        json={"shock_type": "demand_crash"},
    )

    assert resp.status_code == 429
    assert "queue" in resp.json()["detail"].lower()
