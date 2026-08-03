# Spec 015 slice 15.6 — experiments summary REST (Research Lab viewer).
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from market_abm.api.app import create_app
from market_abm.worker.process import WorkerState


def _worker() -> MagicMock:
    w = MagicMock()
    w.state = WorkerState.IDLE
    w.tick_counter = MagicMock()
    w.tick_counter.value = 0
    return w


def _seed_experiment(root: Path, experiment_id: str) -> Path:
    exp = root / experiment_id
    agg = exp / "aggregate"
    agg.mkdir(parents=True)
    rows = [
        {
            "metric": "median_price",
            "ml_share": 0.0,
            "window": "post_burn_in",
            "mean": 12.5,
            "lo": 11.0,
            "hi": 14.0,
            "std": 1.0,
            "n_runs": 3,
        },
        {
            "metric": "hhi",
            "ml_share": 0.5,
            "window": "post_burn_in",
            "mean": 1500.0,
            "lo": 1400.0,
            "hi": 1600.0,
            "std": 50.0,
            "n_runs": 3,
        },
    ]
    (agg / "summary.json").write_text(json.dumps(rows) + "\n", encoding="utf-8")
    fig = exp / "figures"
    fig.mkdir(parents=True)
    (fig / "F1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return exp


def test_15_6_t1_experiments_summary_endpoint(tmp_path: Path) -> None:
    """15.6-T1: GET summary 200 + mean fields."""
    _seed_experiment(tmp_path, "paper_grid_v1")
    app = create_app(worker=_worker(), experiments_dir=str(tmp_path))
    client = TestClient(app)

    listed = client.get("/api/v1/experiments")
    assert listed.status_code == 200
    body = listed.json()
    assert "paper_grid_v1" in body["experiments"]

    summary = client.get("/api/v1/experiments/paper_grid_v1/summary")
    assert summary.status_code == 200
    rows = summary.json()["rows"]
    assert len(rows) >= 1
    assert "mean" in rows[0]
    assert rows[0]["metric"] == "median_price"
    assert rows[0]["mean"] == 12.5


def test_15_6_experiments_figure_endpoint(tmp_path: Path) -> None:
    _seed_experiment(tmp_path, "paper_grid_v1")
    app = create_app(worker=_worker(), experiments_dir=str(tmp_path))
    client = TestClient(app)
    listed = client.get("/api/v1/experiments/paper_grid_v1/figures")
    assert listed.status_code == 200
    assert "F1.png" in listed.json()["figures"]
    resp = client.get("/api/v1/experiments/paper_grid_v1/figures/F1.png")
    assert resp.status_code == 200
    assert resp.content.startswith(b"\x89PNG")


def test_summary_includes_figures_and_warnings(tmp_path: Path) -> None:
    exp = _seed_experiment(tmp_path, "paper_grid_v1")
    (exp / "aggregate" / "warnings.json").write_text(
        '["ml_registry=research_stub"]\n',
        encoding="utf-8",
    )
    app = create_app(worker=_worker(), experiments_dir=str(tmp_path))
    client = TestClient(app)
    summary = client.get("/api/v1/experiments/paper_grid_v1/summary")
    assert summary.status_code == 200
    body = summary.json()
    assert "F1.png" in body["figures"]
    assert body["warnings"] == ["ml_registry=research_stub"]
