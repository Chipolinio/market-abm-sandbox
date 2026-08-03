# Spec 015 §10 — read-only experiment artifact API (Research Lab viewer).
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/experiments", tags=["experiments"])

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_FIGURE = re.compile(r"^F[1-5]\.(png|pdf)$")


class ExperimentListResponse(BaseModel):
    experiments: list[str] = Field(default_factory=list)


class ExperimentSummaryResponse(BaseModel):
    experiment_id: str
    rows: list[dict]


def _experiments_root(request: Request) -> Path:
    raw = getattr(request.app.state, "experiments_dir", None)
    if not raw:
        raise HTTPException(status_code=503, detail="experiments_dir not configured")
    root = Path(raw)
    if not root.is_dir():
        raise HTTPException(status_code=503, detail="experiments_dir missing on disk")
    return root


def _validate_experiment_id(experiment_id: str) -> str:
    if not _SAFE_ID.match(experiment_id):
        raise HTTPException(status_code=400, detail="invalid experiment_id")
    return experiment_id


@router.get("", response_model=ExperimentListResponse)
def list_experiments(request: Request) -> ExperimentListResponse:
    root = _experiments_root(request)
    ids = sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and (p / "aggregate" / "summary.json").is_file()
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
