# Spec 015 slice 15.4 — burn-in filter + Student-t CI95 aggregate.
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from experiments.aggregate import (
    aggregate_experiment_dir,
    aggregate_runs,
    apply_burn_in,
    student_t_ci95,
)


def _tick_frame(n_ticks: int, *, median_price: float = 10.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "tick_id": list(range(n_ticks)),
            "median_price": [median_price + i * 0.0 for i in range(n_ticks)],
            "price_std": [1.0] * n_ticks,
            "hhi": [1000.0] * n_ticks,
            "consumer_surplus_proxy": [5.0] * n_ticks,
            "producer_surplus": [2.0] * n_ticks,
            "platform_profit": [1.0] * n_ticks,
            "gmv": [50.0] * n_ticks,
            "n_tx": [3] * n_ticks,
        }
    )


def test_15_4_t1_burn_in_drops_prefix() -> None:
    """15.4-T1: ticks 0..99 dropped when burn_in=100."""
    df = _tick_frame(150)
    out = apply_burn_in(df, burn_in_ticks=100)
    assert out.height == 50
    assert int(out["tick_id"].min()) == 100
    assert int(out["tick_id"].max()) == 149


def test_15_4_t2_ci_contains_mean() -> None:
    """15.4-T2: Student-t CI satisfies lo ≤ mean ≤ hi."""
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0], dtype=np.float64)
    mean, lo, hi = student_t_ci95(values)
    assert lo <= mean <= hi
    # Known: mean of 1..5 is 3.0
    assert mean == pytest.approx(3.0)


def test_15_4_t3_aggregate_by_ml_share(tmp_path: Path) -> None:
    """15.4-T3: summary has one row group per share × metric."""
    runs = [
        (0.0, 0, _tick_frame(20, median_price=10.0)),
        (0.0, 1, _tick_frame(20, median_price=12.0)),
        (0.5, 0, _tick_frame(20, median_price=20.0)),
        (0.5, 1, _tick_frame(20, median_price=22.0)),
    ]
    summary = aggregate_runs(runs, burn_in_ticks=5)
    assert "metric" in summary.columns
    assert "ml_share" in summary.columns
    assert "mean" in summary.columns
    assert "lo" in summary.columns
    assert "hi" in summary.columns
    assert "window" in summary.columns

    shares = set(summary["ml_share"].to_list())
    assert shares == {0.0, 0.5}
    metrics = set(summary["metric"].to_list())
    assert "median_price" in metrics
    assert "hhi" in metrics

    # One row per (ml_share, metric, window)
    keys = summary.select(["ml_share", "metric", "window"]).unique()
    assert keys.height == summary.height

    price_0 = summary.filter(
        (pl.col("ml_share") == 0.0) & (pl.col("metric") == "median_price")
    )
    assert price_0.height == 1
    assert float(price_0["mean"][0]) == pytest.approx(11.0)  # mean of run means 10 and 12


def test_15_4_aggregate_experiment_dir_writes_artifacts(tmp_path: Path) -> None:
    """Discover run tick_metrics on disk and write aggregate/summary.*."""
    out = tmp_path / "exp"
    for share, run_i, price in [(0.0, 0, 10.0), (0.0, 1, 14.0)]:
        run_dir = out / f"ml_{share:.2f}" / f"run_{run_i:03d}"
        run_dir.mkdir(parents=True)
        _tick_frame(15, median_price=price).write_parquet(run_dir / "tick_metrics.parquet")
        (run_dir / "run_meta.json").write_text(
            f'{{"seed": 1, "ml_share": {share}, "run_index": {run_i}, "manifest_id": "t"}}\n',
            encoding="utf-8",
        )

    summary = aggregate_experiment_dir(out, burn_in_ticks=2)
    assert (out / "aggregate" / "summary.parquet").is_file()
    assert (out / "aggregate" / "summary.json").is_file()
    assert summary.height > 0
