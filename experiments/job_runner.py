# Spec 015.1 — single research job lock, persisted status, background execute.
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from experiments.aggregate import aggregate_experiment_dir
from experiments.batch_runner import run_experiment
from experiments.manifest import ExperimentManifest, ShockProtocolSpec

_LOCK = threading.Lock()
_ACTIVE_JOB_ID: str | None = None
_ACTIVE_EXPERIMENT_ID: str | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jobs_dir(experiments_dir: Path) -> Path:
    d = experiments_dir / "_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def read_job_status(experiments_dir: Path, job_id: str) -> dict[str, Any] | None:
    path = _jobs_dir(experiments_dir) / f"{job_id}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_current_job(experiments_dir: Path) -> dict[str, Any] | None:
    path = _jobs_dir(experiments_dir) / "current.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data:
        return None
    job_id = data.get("job_id")
    if not job_id:
        return None
    return read_job_status(experiments_dir, str(job_id))


def update_job_status(
    experiments_dir: Path,
    job_id: str,
    *,
    status: str,
    experiment_id: str,
    done: int = 0,
    total: int = 0,
    current_ml_share: float | None = None,
    current_run_index: int | None = None,
    error: str | None = None,
    warnings: list[str] | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    existing = read_job_status(experiments_dir, job_id) or {}
    started = started_at or existing.get("started_at") or _utc_now()
    finished_at = existing.get("finished_at")
    if status in ("DONE", "FAILED") and not finished_at:
        finished_at = _utc_now()
    payload: dict[str, Any] = {
        "job_id": job_id,
        "experiment_id": experiment_id,
        "status": status,
        "done": int(done),
        "total": int(total),
        "current_ml_share": current_ml_share,
        "current_run_index": current_run_index,
        "error": error,
        "warnings": warnings if warnings is not None else existing.get("warnings", []),
        "started_at": started,
        "finished_at": finished_at,
    }
    jobs = _jobs_dir(experiments_dir)
    _atomic_write_json(jobs / f"{job_id}.json", payload)
    _atomic_write_json(jobs / "current.json", {"job_id": job_id})
    return payload


def try_acquire_job_lock(experiment_id: str) -> tuple[bool, str | None]:
    """Return (ok, active_experiment_id_if_busy)."""
    global _ACTIVE_JOB_ID, _ACTIVE_EXPERIMENT_ID
    with _LOCK:
        if _ACTIVE_JOB_ID is not None:
            return False, _ACTIVE_EXPERIMENT_ID
        _ACTIVE_EXPERIMENT_ID = experiment_id
        _ACTIVE_JOB_ID = "pending"
        return True, None


def bind_active_job(job_id: str, experiment_id: str) -> None:
    global _ACTIVE_JOB_ID, _ACTIVE_EXPERIMENT_ID
    with _LOCK:
        _ACTIVE_JOB_ID = job_id
        _ACTIVE_EXPERIMENT_ID = experiment_id


def release_job_lock() -> None:
    global _ACTIVE_JOB_ID, _ACTIVE_EXPERIMENT_ID
    with _LOCK:
        _ACTIVE_JOB_ID = None
        _ACTIVE_EXPERIMENT_ID = None


def reset_job_lock_for_tests() -> None:
    """Test helper — clear in-process lock between cases."""
    release_job_lock()


def mark_stale_running_jobs_failed(experiments_dir: Path) -> None:
    """On API startup: RUNNING left on disk → FAILED (Spec 015.1 §14 #8)."""
    jobs = _jobs_dir(experiments_dir)
    current = jobs / "current.json"
    if not current.is_file():
        return
    meta = json.loads(current.read_text(encoding="utf-8"))
    job_id = meta.get("job_id")
    if not job_id:
        return
    status = read_job_status(experiments_dir, str(job_id))
    if status and status.get("status") == "RUNNING":
        update_job_status(
            experiments_dir,
            str(job_id),
            status="FAILED",
            experiment_id=str(status.get("experiment_id", "unknown")),
            done=int(status.get("done", 0)),
            total=int(status.get("total", 0)),
            error="api_restart_while_running",
            warnings=list(status.get("warnings") or []),
            started_at=status.get("started_at"),
        )


def request_to_manifest(body: dict[str, Any], *, output_dir: Path) -> ExperimentManifest:
    shock_raw = body.get("shock_protocol")
    shock = ShockProtocolSpec.model_validate(shock_raw) if shock_raw else None
    return ExperimentManifest.model_validate(
        {
            "experiment_id": body["experiment_id"],
            "base_seed": int(body.get("base_seed", 10_000)),
            "n_runs": int(body["n_runs"]),
            "n_ticks": int(body["n_ticks"]),
            "burn_in_ticks": int(body.get("burn_in_ticks", 0)),
            "ml_share_grid": list(body["ml_share_grid"]),
            "runtime_mode": body.get("runtime_mode", "legacy"),
            "output_dir": str(output_dir),
            "shock_protocol": shock.model_dump() if shock else None,
            "n_buyers": int(body.get("n_buyers", 50)),
            "n_sellers": int(body.get("n_sellers", 8)),
        }
    )


def execute_experiment_job(
    job_id: str,
    experiments_dir: Path,
    request_body: dict[str, Any],
) -> None:
    """
    Run batch → aggregate → figures (best-effort). Always releases lock in finally.
    """
    experiment_id = str(request_body["experiment_id"])
    warnings: list[str] = []
    total = int(request_body["n_runs"]) * len(request_body["ml_share_grid"])
    try:
        update_job_status(
            experiments_dir,
            job_id,
            status="RUNNING",
            experiment_id=experiment_id,
            done=0,
            total=total,
        )
        out = experiments_dir / experiment_id
        out.mkdir(parents=True, exist_ok=True)
        manifest = request_to_manifest(request_body, output_dir=out)
        jobs = int(request_body.get("jobs", 1))

        def _on_progress(
            done: int,
            total_runs: int,
            ml_share: float,
            run_index: int,
        ) -> None:
            update_job_status(
                experiments_dir,
                job_id,
                status="RUNNING",
                experiment_id=experiment_id,
                done=done,
                total=total_runs,
                current_ml_share=ml_share,
                current_run_index=run_index,
                warnings=warnings,
            )

        index = run_experiment(
            manifest,
            jobs=jobs,
            on_progress=_on_progress,
        )
        # Deduplicate run-level warnings (e.g. ml_registry=research_stub).
        seen: set[str] = set()
        for run_meta in index.get("runs", []):
            for w in run_meta.get("warnings") or []:
                msg = str(w)
                if msg not in seen:
                    seen.add(msg)
                    warnings.append(msg)
        burn_in = int(request_body.get("burn_in_ticks", 0))
        summary = aggregate_experiment_dir(out, burn_in_ticks=burn_in)
        try:
            from experiments.figures import render_all_figures
            from experiments.tick_path import write_figure_inputs
            import polars as pl

            fig_meta = write_figure_inputs(out, burn_in_ticks=burn_in)
            for w in fig_meta.get("warnings", []):
                msg = str(w)
                if msg not in seen:
                    seen.add(msg)
                    warnings.append(msg)
            tick_path = pl.read_parquet(out / "aggregate" / "tick_path.parquet")
            zipf = pl.read_parquet(out / "aggregate" / "zipf.parquet")
            render_all_figures(
                out / "figures",
                summary=summary,
                tick_path=tick_path,
                zipf=zipf,
            )
            fig_names = sorted(
                p.name for p in (out / "figures").glob("F*.png")
            )
            (out / "aggregate" / "figures_index.json").write_text(
                json.dumps({"figures": fig_names}, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001 — figures best-effort
            warnings.append(f"figures_failed: {exc}")

        (out / "aggregate" / "warnings.json").write_text(
            json.dumps(warnings, indent=2) + "\n",
            encoding="utf-8",
        )
        update_job_status(
            experiments_dir,
            job_id,
            status="DONE",
            experiment_id=experiment_id,
            done=total,
            total=total,
            warnings=warnings,
        )
    except Exception as exc:  # noqa: BLE001 — persist FAILED
        update_job_status(
            experiments_dir,
            job_id,
            status="FAILED",
            experiment_id=experiment_id,
            done=0,
            total=total,
            error=str(exc),
            warnings=warnings,
        )
    finally:
        release_job_lock()


def start_experiment_job_background(
    experiments_dir: Path,
    request_body: dict[str, Any],
    *,
    execute_fn: Callable[[str, Path, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """
    Acquire lock, persist RUNNING stub, spawn daemon thread.
    Returns accepted payload {job_id, experiment_id, status}.
    Raises RuntimeError with experiment_id if busy (caller → 409).
    """
    experiment_id = str(request_body["experiment_id"])
    ok, busy_id = try_acquire_job_lock(experiment_id)
    if not ok:
        raise RuntimeError(busy_id or "unknown")

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    bind_active_job(job_id, experiment_id)
    total = int(request_body["n_runs"]) * len(request_body["ml_share_grid"])
    update_job_status(
        experiments_dir,
        job_id,
        status="RUNNING",
        experiment_id=experiment_id,
        done=0,
        total=total,
    )

    worker = execute_fn or execute_experiment_job
    thread = threading.Thread(
        target=worker,
        args=(job_id, experiments_dir, request_body),
        daemon=True,
        name=f"experiment-job-{job_id}",
    )
    thread.start()
    return {
        "job_id": job_id,
        "experiment_id": experiment_id,
        "status": "RUNNING",
    }
