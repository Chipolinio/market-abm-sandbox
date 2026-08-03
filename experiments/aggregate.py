# Spec 015 §7 — burn-in filter + Student-t CI95 across paired runs.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import polars as pl
from scipy import stats

METRIC_COLUMNS: tuple[str, ...] = (
    "median_price",
    "price_std",
    "hhi",
    "consumer_surplus_proxy",
    "producer_surplus",
    "platform_profit",
    "gmv",
    "n_tx",
)

_WINDOW_POST_BURN_IN: str = "post_burn_in"


def apply_burn_in(tick_metrics: pl.DataFrame, *, burn_in_ticks: int) -> pl.DataFrame:
    """Drop ticks with tick_id < burn_in_ticks."""
    if burn_in_ticks < 0:
        raise ValueError("burn_in_ticks must be >= 0")
    if "tick_id" not in tick_metrics.columns:
        raise ValueError("tick_metrics must contain tick_id")
    return tick_metrics.filter(pl.col("tick_id") >= int(burn_in_ticks))


def student_t_ci95(values: np.ndarray | Sequence[float]) -> tuple[float, float, float]:
    """
    Two-sided 95% Student-t CI via scipy.stats.t.interval (Spec 015 §19 #10).
    Returns (mean, lo, hi). n<2 → mean with lo=hi=mean.
    """
    arr = np.asarray(values, dtype=np.float64).ravel()
    arr = arr[np.isfinite(arr)]
    n = int(arr.size)
    if n == 0:
        return 0.0, 0.0, 0.0
    mean = float(np.mean(arr))
    if n == 1:
        return mean, mean, mean
    sem = float(stats.sem(arr, ddof=1))
    if sem == 0.0 or not np.isfinite(sem):
        return mean, mean, mean
    lo, hi = stats.t.interval(0.95, df=n - 1, loc=mean, scale=sem)
    return mean, float(lo), float(hi)


def _per_run_metric_means(
    tick_metrics: pl.DataFrame,
    *,
    burn_in_ticks: int,
) -> dict[str, float]:
    filtered = apply_burn_in(tick_metrics, burn_in_ticks=burn_in_ticks)
    if filtered.height == 0:
        return {m: 0.0 for m in METRIC_COLUMNS if m in tick_metrics.columns}
    out: dict[str, float] = {}
    for metric in METRIC_COLUMNS:
        if metric not in filtered.columns:
            continue
        out[metric] = float(filtered[metric].cast(pl.Float64).mean())
    return out


def aggregate_runs(
    runs: Sequence[tuple[float, int, pl.DataFrame]],
    *,
    burn_in_ticks: int,
    window: str = _WINDOW_POST_BURN_IN,
) -> pl.DataFrame:
    """
    Aggregate tick_metrics across runs.

    runs: sequence of (ml_share, run_index, tick_metrics_df)
    For each run → mean of each metric after burn-in.
    Across runs with the same ml_share → Student-t mean/lo/hi.
    Long format columns: metric, ml_share, window, mean, lo, hi, std, n_runs.
    """
    per_share: dict[float, dict[str, list[float]]] = {}
    for ml_share, _run_index, frame in runs:
        means = _per_run_metric_means(frame, burn_in_ticks=burn_in_ticks)
        bucket = per_share.setdefault(float(ml_share), {})
        for metric, value in means.items():
            bucket.setdefault(metric, []).append(value)

    rows: list[dict[str, Any]] = []
    for ml_share, metrics in sorted(per_share.items(), key=lambda x: x[0]):
        for metric, values in sorted(metrics.items()):
            arr = np.asarray(values, dtype=np.float64)
            mean, lo, hi = student_t_ci95(arr)
            std = float(np.std(arr, ddof=1)) if arr.size > 1 else 0.0
            rows.append(
                {
                    "metric": metric,
                    "ml_share": float(ml_share),
                    "window": window,
                    "mean": mean,
                    "lo": lo,
                    "hi": hi,
                    "std": std,
                    "n_runs": int(arr.size),
                }
            )
    return pl.DataFrame(rows)


def _discover_run_metrics(output_dir: Path) -> list[tuple[float, int, pl.DataFrame]]:
    runs: list[tuple[float, int, pl.DataFrame]] = []
    for meta_path in sorted(output_dir.glob("ml_*/run_*/run_meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        metrics_path = meta_path.parent / "tick_metrics.parquet"
        if not metrics_path.is_file():
            continue
        runs.append(
            (
                float(meta["ml_share"]),
                int(meta["run_index"]),
                pl.read_parquet(metrics_path),
            )
        )
    return runs


def aggregate_experiment_dir(
    output_dir: Path | str,
    *,
    burn_in_ticks: int,
    window: str = _WINDOW_POST_BURN_IN,
) -> pl.DataFrame:
    """Load all run tick_metrics under output_dir; write aggregate/summary.parquet+json."""
    root = Path(output_dir)
    runs = _discover_run_metrics(root)
    if not runs:
        raise FileNotFoundError(f"no tick_metrics found under {root}")
    summary = aggregate_runs(runs, burn_in_ticks=burn_in_ticks, window=window)
    agg_dir = root / "aggregate"
    agg_dir.mkdir(parents=True, exist_ok=True)
    summary.write_parquet(agg_dir / "summary.parquet")
    payload = summary.to_dicts()
    (agg_dir / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary
