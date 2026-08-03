# Spec 015.1 slice 15.7 — experiment job API (202 / 409 / persisted status).
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from experiments.job_runner import reset_job_lock_for_tests
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


def _client(tmp_path: Path) -> tuple[TestClient, Path]:
    root = tmp_path / "experiments"
    root.mkdir(parents=True)
    app = create_app(worker=_worker(), experiments_dir=str(root))
    return TestClient(app), root


def _smoke_body(**overrides: object) -> dict:
    body: dict = {
        "experiment_id": "exp_smoke_1",
        "preset": "smoke",
        "ml_share_grid": [0.0],
        "n_runs": 1,
        "n_ticks": 2,
        "burn_in_ticks": 0,
        "jobs": 1,
        "runtime_mode": "legacy",
        "n_buyers": 12,
        "n_sellers": 3,
        "base_seed": 7,
    }
    body.update(overrides)
    return body


def _patch_slow_job(
    monkeypatch: pytest.MonkeyPatch,
    *,
    started: threading.Event,
    release: threading.Event,
    summary_rows: list | None = None,
    total: int = 1,
) -> None:
    def _slow_execute(job_id: str, experiments_dir: Path, request_body: dict) -> None:
        from experiments import job_runner as jr

        try:
            jr.update_job_status(
                experiments_dir,
                job_id,
                status="RUNNING",
                done=0,
                total=total,
                experiment_id=request_body["experiment_id"],
            )
            started.set()
            release.wait(timeout=5)
            exp_id = request_body["experiment_id"]
            agg = experiments_dir / exp_id / "aggregate"
            agg.mkdir(parents=True, exist_ok=True)
            rows = summary_rows if summary_rows is not None else []
            (agg / "summary.json").write_text(
                json.dumps(rows) + "\n", encoding="utf-8"
            )
            jr.update_job_status(
                experiments_dir,
                job_id,
                status="DONE",
                done=total,
                total=total,
                experiment_id=exp_id,
            )
        finally:
            jr.release_job_lock()

    monkeypatch.setattr(
        "experiments.job_runner.execute_experiment_job",
        _slow_execute,
    )


def test_15_7_t1_post_run_returns_202_immediately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15.7-T1: POST smoke → 202 fast; job eventually DONE."""
    client, root = _client(tmp_path)
    release = threading.Event()
    started = threading.Event()
    _patch_slow_job(monkeypatch, started=started, release=release)

    t0 = time.perf_counter()
    resp = client.post("/api/v1/experiments/run", json=_smoke_body())
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 202
    assert elapsed < 1.0
    payload = resp.json()
    assert payload["status"] == "RUNNING"
    assert payload["experiment_id"] == "exp_smoke_1"
    job_id = payload["job_id"]

    assert started.wait(timeout=2)
    release.set()
    for _ in range(50):
        cur = client.get("/api/v1/experiments/jobs/current").json()
        if cur.get("job") and cur["job"]["status"] == "DONE":
            break
        time.sleep(0.05)
    else:
        pytest.fail("job did not reach DONE")
    assert (root / "_jobs" / f"{job_id}.json").is_file()


def test_15_7_t2_second_post_while_running_409(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15.7-T2: while RUNNING → second POST 409."""
    client, _root = _client(tmp_path)
    release = threading.Event()
    started = threading.Event()
    _patch_slow_job(monkeypatch, started=started, release=release)

    first = client.post("/api/v1/experiments/run", json=_smoke_body())
    assert first.status_code == 202
    assert started.wait(timeout=2)

    second = client.post(
        "/api/v1/experiments/run",
        json=_smoke_body(experiment_id="exp_smoke_2"),
    )
    assert second.status_code == 409
    assert "exp_smoke_1" in second.json()["detail"]

    release.set()
    time.sleep(0.1)


def test_15_7_t3_jobs_current_running_then_done(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15.7-T3: current RUNNING then DONE; summary path exists."""
    client, root = _client(tmp_path)
    release = threading.Event()
    started = threading.Event()
    _patch_slow_job(
        monkeypatch,
        started=started,
        release=release,
        summary_rows=[
            {
                "metric": "median_price",
                "ml_share": 0.0,
                "window": "post_burn_in",
                "mean": 1.0,
                "lo": 1.0,
                "hi": 1.0,
                "std": 0.0,
                "n_runs": 1,
            }
        ],
    )

    client.post("/api/v1/experiments/run", json=_smoke_body())
    assert started.wait(timeout=2)
    cur = client.get("/api/v1/experiments/jobs/current").json()
    assert cur["job"]["status"] == "RUNNING"

    release.set()
    for _ in range(50):
        cur = client.get("/api/v1/experiments/jobs/current").json()
        if cur["job"]["status"] == "DONE":
            break
        time.sleep(0.05)
    assert cur["job"]["status"] == "DONE"
    summary = client.get("/api/v1/experiments/exp_smoke_1/summary")
    assert summary.status_code == 200
    assert summary.json()["rows"][0]["mean"] == 1.0
    assert (root / "exp_smoke_1" / "aggregate" / "summary.json").is_file()


def test_15_7_t4_job_status_persisted_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """15.7-T4: _jobs/{job_id}.json exists with done/total."""
    client, root = _client(tmp_path)
    release = threading.Event()
    started = threading.Event()
    _patch_slow_job(monkeypatch, started=started, release=release, total=2)

    resp = client.post("/api/v1/experiments/run", json=_smoke_body())
    job_id = resp.json()["job_id"]
    assert started.wait(timeout=2)
    path = root / "_jobs" / f"{job_id}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["total"] == 2
    assert "done" in data
    release.set()


def test_15_7_jobs_current_null_when_idle(tmp_path: Path) -> None:
    client, _root = _client(tmp_path)
    cur = client.get("/api/v1/experiments/jobs/current")
    assert cur.status_code == 200
    assert cur.json() == {"job": None}
