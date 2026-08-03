# Spec 015 / 015.1 — experiment artifacts + Launch job API.
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from experiments.job_runner import (
    mark_stale_running_jobs_failed,
    read_current_job,
    read_job_status,
    reset_job_lock_for_tests,
    start_experiment_job_background,
)

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_FIGURE = re.compile(r"^F[1-5]\.(png|pdf)$")


class ExperimentListResponse(BaseModel):
    experiments: list[str] = Field(default_factory=list)


class ExperimentSummaryResponse(BaseModel):
    experiment_id: str
    rows: list[dict]


class ExperimentRunRequest(BaseModel):
    experiment_id: str = Field(min_length=1, max_length=64)
    preset: Literal["smoke", "paper", "custom"] = "smoke"
    ml_share_grid: list[float] = Field(min_length=1)
    n_runs: int = Field(ge=1, le=500)
    n_ticks: int = Field(ge=1, le=100_000)
    burn_in_ticks: int = Field(default=0, ge=0)
    jobs: int = Field(default=1, ge=1, le=32)
    runtime_mode: Literal["legacy", "extended"] = "legacy"
    n_buyers: int = Field(default=50, ge=2)
    n_sellers: int = Field(default=8, ge=1)
    base_seed: int = 10_000
    shock_protocol: dict[str, Any] | None = None


class ExperimentRunAccepted(BaseModel):
    job_id: str
    experiment_id: str
    status: str


class JobStatusDTO(BaseModel):
    job_id: str
    experiment_id: str
    status: str
    done: int = 0
    total: int = 0
    current_ml_share: float | None = None
    current_run_index: int | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    started_at: str | None = None
    finished_at: str | None = None


class CurrentJobResponse(BaseModel):
    job: JobStatusDTO | None = None


def _experiments_root(request: Request) -> Path:
    raw = getattr(request.app.state, "experiments_dir", None)
    if not raw:
        raise HTTPException(status_code=503, detail="experiments_dir not configured")
    root = Path(raw)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _validate_experiment_id(experiment_id: str) -> str:
    if not _SAFE_ID.match(experiment_id):
        raise HTTPException(status_code=400, detail="invalid experiment_id")
    return experiment_id


@router.post("/run", status_code=202, response_model=ExperimentRunAccepted)
def start_experiment_run(
    body: ExperimentRunRequest,
    request: Request,
) -> ExperimentRunAccepted | JSONResponse:
    root = _experiments_root(request)
    experiment_id = _validate_experiment_id(body.experiment_id)
    for share in body.ml_share_grid:
        if share < 0.0 or share > 1.0:
            raise HTTPException(status_code=400, detail="ml_share_grid values must be in [0, 1]")
    payload = body.model_dump()
    payload["experiment_id"] = experiment_id
    try:
        accepted = start_experiment_job_background(root, payload)
    except RuntimeError as exc:
        busy = str(exc)
        return JSONResponse(
            status_code=409,
            content={
                "detail": f"Another experiment job ({busy}) is currently running.",
            },
        )
    return ExperimentRunAccepted.model_validate(accepted)


@router.get("/jobs/current", response_model=CurrentJobResponse)
def get_current_job(request: Request) -> CurrentJobResponse:
    root = _experiments_root(request)
    raw = read_current_job(root)
    if raw is None:
        return CurrentJobResponse(job=None)
    return CurrentJobResponse(job=JobStatusDTO.model_validate(raw))


@router.get("/jobs/{job_id}", response_model=JobStatusDTO)
def get_job(job_id: str, request: Request) -> JobStatusDTO:
    root = _experiments_root(request)
    raw = read_job_status(root, job_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusDTO.model_validate(raw)


@router.get("", response_model=ExperimentListResponse)
def list_experiments(request: Request) -> ExperimentListResponse:
    root = _experiments_root(request)
    ids = sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and p.name != "_jobs"
        and (p / "aggregate" / "summary.json").is_file()
    )
    return ExperimentListResponse(experiments=ids)


@router.get("/{experiment_id}/summary", response_model=ExperimentSummaryResponse)
def get_experiment_summary(
    experiment_id: str,
    request: Request,
) -> ExperimentSummaryResponse:
    experiment_id = _validate_experiment_id(experiment_id)
    root = _experiments_root(request)
    summary_path = root / experiment_id / "aggregate" / "summary.json"
    if not summary_path.is_file():
        raise HTTPException(status_code=404, detail="experiment summary not found")
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise HTTPException(status_code=500, detail="summary.json must be a list of rows")
    return ExperimentSummaryResponse(experiment_id=experiment_id, rows=payload)


@router.get("/{experiment_id}/figures/{figure_name}")
def get_experiment_figure(
    experiment_id: str,
    figure_name: str,
    request: Request,
) -> FileResponse:
    experiment_id = _validate_experiment_id(experiment_id)
    if not _SAFE_FIGURE.match(figure_name):
        raise HTTPException(status_code=400, detail="invalid figure name")
    root = _experiments_root(request)
    path = (root / experiment_id / "figures" / figure_name).resolve()
    figures_root = (root / experiment_id / "figures").resolve()
    if not str(path).startswith(str(figures_root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="figure not found")
    media = "image/png" if figure_name.endswith(".png") else "application/pdf"
    return FileResponse(path, media_type=media)


# Re-export for tests
__all__ = [
    "router",
    "reset_job_lock_for_tests",
    "mark_stale_running_jobs_failed",
]
