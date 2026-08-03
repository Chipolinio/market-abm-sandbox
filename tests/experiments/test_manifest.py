# Spec 015 slice 15.1 — ExperimentManifest YAML load.
from __future__ import annotations

from pathlib import Path

from experiments.manifest import ExperimentManifest, load_manifest


def test_15_1_t2_manifest_loads_grid(tmp_path: Path) -> None:
    """15.1-T2: YAML → n_runs, ml_share_grid, burn_in."""
    path = tmp_path / "paper_grid_smoke.yaml"
    path.write_text(
        """
experiment_id: smoke_grid
base_seed: 10000
n_runs: 30
n_ticks: 500
burn_in_ticks: 100
ml_share_grid: [0.0, 0.25, 0.5, 0.75, 1.0]
runtime_mode: extended
output_dir: output/experiments/smoke_grid
shock_protocol:
  mode: fixed_duration
  demand_crash_at_tick: 200
  scenario: severe
""".strip()
        + "\n",
        encoding="utf-8",
    )
    manifest = load_manifest(path)
    assert isinstance(manifest, ExperimentManifest)
    assert manifest.experiment_id == "smoke_grid"
    assert manifest.base_seed == 10_000
    assert manifest.n_runs == 30
    assert manifest.n_ticks == 500
    assert manifest.burn_in_ticks == 100
    assert list(manifest.ml_share_grid) == [0.0, 0.25, 0.5, 0.75, 1.0]
    assert manifest.runtime_mode == "extended"
    assert manifest.shock_protocol is not None
    assert manifest.shock_protocol.demand_crash_at_tick == 200
