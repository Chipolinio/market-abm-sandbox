# Honest tick_path / zipf builders for Research Lab figures.
from __future__ import annotations

from pathlib import Path

import polars as pl

from experiments.tick_path import build_tick_path, build_zipf_from_experiment_dir, write_figure_inputs


def _frame(n_ticks: int, *, price: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "tick_id": list(range(n_ticks)),
            "median_price": [price + 0.1 * i for i in range(n_ticks)],
            "mean_listing_price": [price + 1.0] * n_ticks,
            "price_std": [0.5] * n_ticks,
            "hhi": [1000.0] * n_ticks,
            "gmv": [10.0] * n_ticks,
            "n_tx": [2] * n_ticks,
            "consumer_surplus_proxy": [1.0] * n_ticks,
            "producer_surplus": [1.0] * n_ticks,
            "platform_profit": [0.5] * n_ticks,
        }
    )


def test_build_tick_path_aggregates_across_runs() -> None:
    runs = [
        (0.0, 0, _frame(5, price=10.0)),
        (0.0, 1, _frame(5, price=12.0)),
        (1.0, 0, _frame(5, price=20.0)),
    ]
    path = build_tick_path(runs, metric="median_price", burn_in_ticks=0)
    assert path.height == 10  # 5 ticks × 2 shares
    row = path.filter((pl.col("ml_share") == 0.0) & (pl.col("tick_id") == 0))
    assert row.height == 1
    assert float(row["median"][0]) == 11.0  # median of 10 and 12
    assert "q25" in path.columns and "q75" in path.columns


def test_write_figure_inputs_persists_parquet(tmp_path: Path) -> None:
    out = tmp_path / "exp"
    for share, run_i, price in [(0.0, 0, 10.0), (0.0, 1, 14.0), (1.0, 0, 20.0)]:
        run_dir = out / f"ml_{share:.2f}" / f"run_{run_i:03d}"
        run_dir.mkdir(parents=True)
        _frame(8, price=price).write_parquet(run_dir / "tick_metrics.parquet")
        (run_dir / "run_meta.json").write_text(
            f'{{"ml_share": {share}, "run_index": {run_i}, "seed": 1}}\n',
            encoding="utf-8",
        )
    meta = write_figure_inputs(out, burn_in_ticks=1)
    assert (out / "aggregate" / "tick_path.parquet").is_file()
    assert (out / "aggregate" / "zipf.parquet").is_file()
    assert (out / "aggregate" / "tick_path_shelf.parquet").is_file()
    assert meta["n_path_rows"] > 0
    # No tx → synthetic zipf warning
    assert any("zipf_fallback" in w for w in meta["warnings"])


def test_zipf_from_transactions_when_present(tmp_path: Path) -> None:
    out = tmp_path / "exp"
    run = out / "ml_1.00" / "run_000"
    tx = run / "sim" / "transactions"
    tx.mkdir(parents=True)
    pl.DataFrame(
        {
            "seller_id": [1, 1, 2, 3],
            "price_paid": [10.0, 5.0, 3.0, 1.0],
        }
    ).write_parquet(tx / "tick_000000.parquet")
    (run / "run_meta.json").write_text(
        '{"ml_share": 1.0, "run_index": 0, "seed": 1}\n',
        encoding="utf-8",
    )
    # need tick_metrics for discover? zipf only needs tx
    zipf, warnings = build_zipf_from_experiment_dir(out)
    assert zipf.height >= 3
    assert not any("fallback" in w for w in warnings)
    assert float(zipf.sort("rank")["sales"][0]) >= float(zipf.sort("rank")["sales"][-1])
