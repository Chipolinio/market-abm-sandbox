# Spec 015 — research batch must differentiate ml_share when ML path is active.
from __future__ import annotations

from pathlib import Path

import polars as pl

from experiments.batch_runner import run_experiment
from experiments.manifest import ExperimentManifest


def _manifest(tmp_path: Path, **overrides: object) -> ExperimentManifest:
    base = {
        "experiment_id": "share_diff",
        "base_seed": 10000,
        "n_runs": 1,
        "n_ticks": 12,
        "burn_in_ticks": 0,
        "ml_share_grid": [0.0, 0.25, 0.5, 1.0],
        "runtime_mode": "legacy",
        "output_dir": str(tmp_path / "exp"),
        "n_buyers": 80,
        "n_sellers": 40,
    }
    base.update(overrides)
    return ExperimentManifest.model_validate(base)


def test_ml_share_grid_metrics_not_identical(tmp_path: Path) -> None:
    """Regression: share>0 without registry used to collapse to bit-identical rules."""
    manifest = _manifest(tmp_path)
    run_experiment(manifest, jobs=1)

    gmv_by_share: dict[float, float] = {}
    for share in manifest.ml_share_grid:
        meta_path = (
            Path(manifest.output_dir)
            / f"ml_{float(share):.2f}"
            / "run_000"
            / "run_meta.json"
        )
        assert meta_path.is_file()
        metrics = pl.read_parquet(meta_path.parent / "tick_metrics.parquet")
        gmv_by_share[float(share)] = float(metrics["gmv"].mean())

    pos = [gmv_by_share[s] for s in (0.25, 0.5, 1.0)]
    assert not (pos[0] == pos[1] == pos[2]), (
        f"positive shares bit-identical (registry not applied): {gmv_by_share}"
    )
    # 0.25 and 1.0 should move apart with stub log-delta on different K sellers
    assert gmv_by_share[0.25] != gmv_by_share[1.0]


def test_small_n_fine_grid_not_plateau(tmp_path: Path) -> None:
    """n=8 + mid shares: shelf prices must differ (tx GMV may still concentrate)."""
    manifest = _manifest(
        tmp_path,
        n_sellers=8,
        n_buyers=80,
        n_ticks=20,
        ml_share_grid=[0.25, 0.5, 0.75],
    )
    run_experiment(manifest, jobs=1)
    shelf = []
    gmvs = []
    for share in manifest.ml_share_grid:
        path = (
            Path(manifest.output_dir)
            / f"ml_{float(share):.2f}"
            / "run_000"
            / "tick_metrics.parquet"
        )
        df = pl.read_parquet(path)
        shelf.append(float(df["mean_listing_price"].mean()))
        gmvs.append(float(df["gmv"].mean()))
    assert len(set(shelf)) == 3, f"shelf plateau: mean_listing_price={shelf} gmv={gmvs}"
