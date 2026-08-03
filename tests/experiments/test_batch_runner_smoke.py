# Spec 015 slice 15.1 — batch_runner smoke, isolation, --jobs.
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from experiments.batch_runner import reset_run_isolation, run_experiment
from experiments.manifest import ExperimentManifest
from experiments.seeds import seed_for_run


def _smoke_manifest(tmp_path: Path, **overrides: object) -> ExperimentManifest:
    base = {
        "experiment_id": "batch_smoke",
        "base_seed": 42,
        "n_runs": 2,
        "n_ticks": 2,
        "burn_in_ticks": 0,
        "ml_share_grid": [0.0],
        "runtime_mode": "legacy",
        "output_dir": str(tmp_path / "exp"),
        "n_buyers": 20,
        "n_sellers": 4,
    }
    base.update(overrides)
    return ExperimentManifest.model_validate(base)


def test_15_1_t3_batch_two_runs_write_meta(tmp_path: Path) -> None:
    """15.1-T3: 2 seeds × 1 share × few ticks → 2 run_meta.json + tick_metrics."""
    manifest = _smoke_manifest(tmp_path)
    index = run_experiment(manifest, jobs=1)
    assert index["experiment_id"] == "batch_smoke"
    assert len(index["runs"]) == 2

    out = Path(manifest.output_dir)
    metas = sorted(out.glob("**/run_meta.json"))
    assert len(metas) == 2
    for meta_path in metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        assert "seed" in meta
        assert meta["ml_share"] == 0.0
        assert meta["manifest_id"] == "batch_smoke"
        tick_metrics = meta_path.parent / "tick_metrics.parquet"
        assert tick_metrics.is_file()
        df = pl.read_parquet(tick_metrics)
        assert df.height == manifest.n_ticks
        assert "tick_id" in df.columns


def test_15_1_t4_paired_seed_across_shares(tmp_path: Path) -> None:
    """15.1-T4: share 0 and 0.5, run_i=0 → identical seed in meta."""
    manifest = _smoke_manifest(
        tmp_path,
        n_runs=1,
        ml_share_grid=[0.0, 0.5],
    )
    index = run_experiment(manifest, jobs=1)
    assert len(index["runs"]) == 2
    seeds = {row["ml_share"]: row["seed"] for row in index["runs"]}
    assert seeds[0.0] == seeds[0.5]
    assert seeds[0.0] == seed_for_run(manifest.base_seed, 0)


def test_15_1_t5_batch_run_isolation(tmp_path: Path) -> None:
    """15.1-T5: two sequential runs — isolation reset prevents leaked marker state."""
    from experiments import batch_runner as br

    # Poison in-process state that reset_run_isolation must clear.
    br._ISOLATION_DIRTY = True
    reset_run_isolation()
    assert br._ISOLATION_DIRTY is False

    br._ISOLATION_DIRTY = True
    manifest = _smoke_manifest(tmp_path, n_runs=2, ml_share_grid=[0.0])
    run_experiment(manifest, jobs=1)
    # After batch, isolation flag must not remain dirty from a prior poison
    # (each run resets before work; final state clean).
    assert br._ISOLATION_DIRTY is False


def test_15_1_t6_batch_jobs_flag_smoke(tmp_path: Path) -> None:
    """15.1-T6: jobs=2 on tiny grid finishes; all run_meta present."""
    manifest = _smoke_manifest(
        tmp_path,
        n_runs=2,
        ml_share_grid=[0.0, 0.5],
    )
    index = run_experiment(manifest, jobs=2)
    assert len(index["runs"]) == 4
    out = Path(manifest.output_dir)
    metas = list(out.glob("**/run_meta.json"))
    assert len(metas) == 4
    # Completion order may differ; seeds/shares set must match paired design.
    by_key = {(r["ml_share"], r["run_index"]): r["seed"] for r in index["runs"]}
    assert by_key[(0.0, 0)] == by_key[(0.5, 0)]
    assert by_key[(0.0, 1)] == by_key[(0.5, 1)]


def test_batch_choice_calibration_produces_transactions(tmp_path: Path) -> None:
    """Research batch must match live choice scale or GMV/HHI collapse to 0."""
    manifest = _smoke_manifest(
        tmp_path,
        n_runs=1,
        n_ticks=10,
        n_buyers=80,
        n_sellers=8,
        base_seed=10000,
    )
    run_experiment(manifest, jobs=1)
    metrics = pl.read_parquet(
        Path(manifest.output_dir) / "ml_0.00" / "run_000" / "tick_metrics.parquet"
    )
    assert int(metrics["n_tx"].sum()) > 0
    assert float(metrics["gmv"].sum()) > 0.0

