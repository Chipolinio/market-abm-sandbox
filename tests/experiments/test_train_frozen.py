# Train / freeze CatBoost + API endpoints for Research Lab.
from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from experiments.job_runner import reset_job_lock_for_tests
from experiments.train_frozen import frozen_registry_status, train_frozen_registry
from market_abm.api.app import create_app
from market_abm.worker.process import WorkerState


@pytest.fixture(autouse=True)
def _clear_job_lock() -> None:
    reset_job_lock_for_tests()
    yield
    reset_job_lock_for_tests()


def _worker() -> MagicMock:
    w = MagicMock()
    w.state = WorkerState.IDLE
    w.tick_counter = MagicMock()
    w.tick_counter.value = 0
    return w


@pytest.mark.ml
def test_train_frozen_registry_writes_ml_dir(tmp_path: Path) -> None:
    frozen = tmp_path / "ml_frozen"
    work = tmp_path / "boot"
    meta = train_frozen_registry(
        frozen_root=frozen,
        work_dir=work,
        n_runs=2,
        n_ticks_per_run=12,
        n_buyers=40,
        n_sellers=12,
        population_seed=7,
        min_rows_per_strategy=10,
    )
    assert meta["present"] is True
    assert (frozen / "ml" / "registry.json").is_file()
    status = frozen_registry_status(frozen)
    assert status["present"] is True
    assert "MaxProfit" in (status.get("strategies") or [])


def test_ml_registry_status_endpoint(tmp_path: Path) -> None:
    frozen = tmp_path / "ml_frozen"
    (frozen / "ml").mkdir(parents=True)
    (frozen / "ml" / "registry.json").write_text(
        json.dumps(
            {
                "strategies": ["MaxProfit", "MaxVolume"],
                "train_config_hash": "sha256:x",
                "catboost_version": "1.2.0",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    app = create_app(
        worker=_worker(),
        experiments_dir=str(tmp_path / "experiments"),
        ml_frozen_dir=str(frozen),
    )
    client = TestClient(app)
    resp = client.get("/api/v1/experiments/ml-registry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["present"] is True
    assert body["strategies"] == ["MaxProfit", "MaxVolume"]


def test_train_ml_endpoint_202_and_409(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "experiments"
    root.mkdir()
    frozen = tmp_path / "ml_frozen"
    app = create_app(
        worker=_worker(),
        experiments_dir=str(root),
        ml_frozen_dir=str(frozen),
    )
    client = TestClient(app)

    started = threading.Event()
    release = threading.Event()

    def _slow(job_id: str, experiments_dir: Path, request_body: dict) -> None:
        from experiments import job_runner as jr

        try:
            jr.update_job_status(
                experiments_dir,
                job_id,
                status="RUNNING",
                experiment_id=request_body["experiment_id"],
                done=0,
                total=2,
            )
            started.set()
            release.wait(timeout=5)
            jr.update_job_status(
                experiments_dir,
                job_id,
                status="DONE",
                experiment_id=request_body["experiment_id"],
                done=2,
                total=2,
                warnings=["ml_registry=frozen_trained"],
            )
        finally:
            jr.release_job_lock()

    monkeypatch.setattr("experiments.job_runner.execute_train_job", _slow)

    resp = client.post("/api/v1/experiments/train-ml", json={})
    assert resp.status_code == 202
    assert resp.json()["experiment_id"] == "ml-train"
    assert started.wait(timeout=2)

    busy = client.post("/api/v1/experiments/train-ml", json={})
    assert busy.status_code == 409

    release.set()
