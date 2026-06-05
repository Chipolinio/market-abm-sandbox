# Тесты CORS middleware для vite dev (Spec 007 §7.6).
from __future__ import annotations

import multiprocessing as mp
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from market_abm.api.app import create_app
from market_abm.worker.process import WorkerState


def _make_mock_worker() -> MagicMock:
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.tick_counter = mp.Value("i", 0)
    worker.state = WorkerState.IDLE
    worker.last_error = None
    worker.run_id = "cors-test"
    return worker


def test_cors_disabled_by_default() -> None:
    client = TestClient(create_app(worker=_make_mock_worker(), enable_cors=False))
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_enabled_returns_allow_origin() -> None:
    client = TestClient(create_app(worker=_make_mock_worker(), enable_cors=True))
    response = client.get(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_preflight_options() -> None:
    client = TestClient(create_app(worker=_make_mock_worker(), enable_cors=True))
    response = client.options(
        "/api/v1/simulation/status",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
