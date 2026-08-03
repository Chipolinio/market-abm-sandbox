# Spec 015 — honest tick_path / zipf builders from experiment run artifacts.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import polars as pl

from experiments.aggregate import apply_burn_in, student_t_ci95
from market_abm.domain.constants import COL_PRICE_PAID, COL_SELLER_ID


def _robust_quantiles(arr: np.ndarray) -> tuple[float, float, float]:
    """median, q25, q75 (finite values only)."""
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return 0.0, 0.0, 0.0
    return (
        float(np.median(finite)),
        float(np.quantile(finite, 0.25)),
        float(np.quantile(finite, 0.75)),
    )


def build_tick_path(
    runs: Sequence[tuple[float, int, pl.DataFrame]],
    *,
    metric: str = "median_price",
    burn_in_ticks: int = 0,
) -> pl.DataFrame:
    """
    Per (ml_share, tick_id): aggregate `metric` across paired runs.

    Columns: tick_id, ml_share, metric, mean, lo, hi, median, q25, q75, n_runs.
    Uses Student-t for mean/lo/hi and quartiles for robust bands (paper F1).
    """
    # bucket[(share, tick)] -> list of values
    bucket: dict[tuple[float, int], list[float]] = {}
    for ml_share, _run_index, frame in runs:
        filtered = apply_burn_in(frame, burn_in_ticks=burn_in_ticks)
        if metric not in filtered.columns or filtered.height == 0:
            continue
        for row in filtered.select(["tick_id", metric]).iter_rows(named=True):
            key = (float(ml_share), int(row["tick_id"]))
            bucket.setdefault(key, []).append(float(row[metric]))

    rows: list[dict[str, Any]] = []
    for (share, tick_id), values in sorted(bucket.items(), key=lambda x: (x[0][0], x[0][1])):
        arr = np.asarray(values, dtype=np.float64)
        mean, lo, hi = student_t_ci95(arr)
        med, q25, q75 = _robust_quantiles(arr)
        rows.append(
            {
                "tick_id": tick_id,
                "ml_share": share,
                "metric": metric,
                "mean": mean,
                "lo": lo,
                "hi": hi,
                "median": med,
                "q25": q25,
                "q75": q75,
                "n_runs": int(arr.size),
            }
        )
    if not rows:
        return pl.DataFrame(
            schema={
                "tick_id": pl.Int64,
                "ml_share": pl.Float64,
                "metric": pl.Utf8,
                "mean": pl.Float64,
                "lo": pl.Float64,
                "hi": pl.Float64,
                "median": pl.Float64,
                "q25": pl.Float64,
                "q75": pl.Float64,
                "n_runs": pl.Int64,
            }
        )
    return pl.DataFrame(rows)


def build_zipf_from_experiment_dir(output_dir: Path | str) -> tuple[pl.DataFrame, list[str]]:
    """
    Rank-size from last available transaction tick per ml_share (honest F5).

    Falls back to a mild synthetic Zipf with a warning when no tx parquet exists
    (e.g. share=0 rules path without persistence).
    """
    root = Path(output_dir)
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []

    share_dirs = sorted(root.glob("ml_*"))
    for share_dir in share_dirs:
        try:
            share = float(share_dir.name.replace("ml_", ""))
        except ValueError:
            continue
        seller_sales: dict[int, float] = {}
        found_tx = False
        for run_dir in sorted(share_dir.glob("run_*")):
            tx_dir = run_dir / "sim" / "transactions"
            if not tx_dir.is_dir():
                continue
            files = sorted(tx_dir.glob("tick_*.parquet"))
            if not files:
                continue
            found_tx = True
            # Use last few ticks for stabler rank-size
            for path in files[-5:]:
                tx = pl.read_parquet(path)
                if tx.height == 0 or COL_SELLER_ID not in tx.columns:
                    continue
                price_col = COL_PRICE_PAID if COL_PRICE_PAID in tx.columns else None
                if price_col is None:
                    continue
                agg = tx.group_by(COL_SELLER_ID).agg(
                    pl.col(price_col).cast(pl.Float64).sum().alias("_sales")
                )
                for sid, sales in zip(
                    agg[COL_SELLER_ID].to_list(),
                    agg["_sales"].to_list(),
                    strict=True,
                ):
                    seller_sales[int(sid)] = seller_sales.get(int(sid), 0.0) + float(sales)

        if not found_tx or not seller_sales:
            warnings.append(f"zipf_fallback_synthetic: ml_share={share}")
            for rank in range(1, 11):
                rows.append(
                    {
                        "ml_share": share,
                        "rank": rank,
                        "sales": 1000.0 / (rank**1.1),
                    }
                )
            continue

        ordered = sorted(seller_sales.values(), reverse=True)
        for rank, sales in enumerate(ordered[:20], start=1):
            rows.append({"ml_share": share, "rank": rank, "sales": max(sales, 1e-9)})

    if not rows:
        warnings.append("zipf_fallback_synthetic: empty_experiment")
        for rank in range(1, 11):
            rows.append({"ml_share": 0.0, "rank": rank, "sales": 1000.0 / (rank**1.1)})
    return pl.DataFrame(rows), warnings


def write_figure_inputs(
    output_dir: Path | str,
    *,
    burn_in_ticks: int,
    price_metric: str = "median_price",
) -> dict[str, Any]:
    """
    Discover runs → write aggregate/tick_path.parquet + zipf.parquet.
    Also writes tick_path_shelf.parquet when mean_listing_price is present.
    Returns meta dict with warnings.
    """
    from experiments.aggregate import _discover_run_metrics

    root = Path(output_dir)
    runs = _discover_run_metrics(root)
    if not runs:
        raise FileNotFoundError(f"no tick_metrics under {root}")

    agg_dir = root / "aggregate"
    agg_dir.mkdir(parents=True, exist_ok=True)

    tick_path = build_tick_path(runs, metric=price_metric, burn_in_ticks=burn_in_ticks)
    tick_path.write_parquet(agg_dir / "tick_path.parquet")

    if any("mean_listing_price" in df.columns for _s, _i, df in runs):
        shelf_path = build_tick_path(
            runs, metric="mean_listing_price", burn_in_ticks=burn_in_ticks
        )
        shelf_path.write_parquet(agg_dir / "tick_path_shelf.parquet")

    zipf, zipf_warnings = build_zipf_from_experiment_dir(root)
    zipf.write_parquet(agg_dir / "zipf.parquet")
    meta = {
        "warnings": zipf_warnings,
        "price_metric": price_metric,
        "n_path_rows": int(tick_path.height),
    }
    (agg_dir / "figure_inputs.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return meta
