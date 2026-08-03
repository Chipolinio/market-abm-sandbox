# Spec 015 §4.3 — headless batch runner (paired seeds, isolation, --jobs).
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import polars as pl

from experiments.manifest import ExperimentManifest
from experiments.seeds import seed_for_run
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import COL_PRICE, COL_PRICE_PAID
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.runner import run_simulation

# In-process isolation probe for tests / soft reset (Spec 015 §4.3.1).
_ISOLATION_DIRTY: bool = False


def reset_run_isolation() -> None:
    """Clear process-local experiment state before a batch run unit."""
    global _ISOLATION_DIRTY
    _ISOLATION_DIRTY = False


def _run_dir(output_dir: Path, *, ml_share: float, run_index: int) -> Path:
    return output_dir / f"ml_{ml_share:.2f}" / f"run_{run_index:03d}"


def _write_tick_metrics(
    path: Path,
    rows: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(path)


def _write_run_meta(path: Path, meta: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _execute_one_run(task: dict[str, Any]) -> dict[str, Any]:
    """
    Execute a single (ml_share, run_index) simulation unit.
    Top-level for ProcessPool pickling; always resets isolation first.
    """
    reset_run_isolation()

    ml_share = float(task["ml_share"])
    run_index = int(task["run_index"])
    base_seed = int(task["base_seed"])
    seed = seed_for_run(base_seed, run_index)
    n_ticks = int(task["n_ticks"])
    n_buyers = int(task["n_buyers"])
    n_sellers = int(task["n_sellers"])
    runtime_mode = task["runtime_mode"]
    experiment_id = str(task["experiment_id"])
    output_dir = Path(task["output_dir"])
    run_root = _run_dir(output_dir, ml_share=ml_share, run_index=run_index)
    run_root.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    # ml_seller_share wiring is Spec 015.3 — record share in meta only for 15.1.
    if ml_share > 0.0:
        warnings.append("ml_share_recorded_pending_assignment_slice")

    buyers = generate_buyers(
        BuyerPopulationConfig.default_market(n_buyers=n_buyers, seed=seed)
    )
    sellers = generate_sellers(
        SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
    )
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=seed,
    )
    config = SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=min(50, max(n_sellers * 2, 8)),
            buyers_batch_size=max(n_buyers, 200),
        ),
        repricing=RepricingConfig.default_market(),
        runtime_mode=runtime_mode,
        persistence=PersistenceConfig(enabled=False, base_dir=str(run_root)),
    )

    metric_rows: list[dict[str, Any]] = []
    for tick_id, products_df, transactions_df in run_simulation(
        buyers, sellers, listings, n_ticks=n_ticks, config=config
    ):
        prices = products_df[COL_PRICE]
        median_price = float(prices.median()) if products_df.height else 0.0
        std_val = float(prices.std()) if products_df.height > 1 else 0.0
        if std_val != std_val:  # NaN
            std_val = 0.0
        gmv = (
            float(transactions_df[COL_PRICE_PAID].sum())
            if transactions_df.height
            else 0.0
        )
        metric_rows.append(
            {
                "tick_id": int(tick_id),
                "median_price": median_price,
                "price_std": std_val,
                "hhi": 0.0,
                "consumer_surplus_proxy": 0.0,
                "producer_surplus": 0.0,
                "platform_profit": 0.0,
                "gmv": gmv,
                "n_tx": int(transactions_df.height),
            }
        )

    _write_tick_metrics(run_root / "tick_metrics.parquet", metric_rows)
    meta = {
        "seed": seed,
        "ml_share": ml_share,
        "run_index": run_index,
        "n_ticks": n_ticks,
        "manifest_id": experiment_id,
        "warnings": warnings,
        "run_dir": str(run_root),
    }
    _write_run_meta(run_root / "run_meta.json", meta)
    return meta


def run_experiment(
    manifest: ExperimentManifest,
    *,
    jobs: int | None = None,
) -> dict[str, Any]:
    """
    Run full ml_share × seed grid. jobs=1 sequential; jobs>1 ProcessPoolExecutor.
    Returns index dict with experiment_id and runs[].
    """
    n_jobs = 1 if jobs is None else int(jobs)
    if n_jobs < 1:
        raise ValueError("jobs must be >= 1")

    output_dir = Path(manifest.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tasks: list[dict[str, Any]] = []
    for ml_share in manifest.ml_share_grid:
        for run_index in range(manifest.n_runs):
            tasks.append(
                {
                    "ml_share": float(ml_share),
                    "run_index": int(run_index),
                    "base_seed": int(manifest.base_seed),
                    "n_ticks": int(manifest.n_ticks),
                    "n_buyers": int(manifest.n_buyers),
                    "n_sellers": int(manifest.n_sellers),
                    "runtime_mode": manifest.runtime_mode,
                    "experiment_id": manifest.experiment_id,
                    "output_dir": str(output_dir),
                }
            )

    results: list[dict[str, Any]] = []
    if n_jobs == 1:
        for task in tasks:
            results.append(_execute_one_run(task))
    else:
        with ProcessPoolExecutor(max_workers=n_jobs) as pool:
            futures = [pool.submit(_execute_one_run, task) for task in tasks]
            for fut in as_completed(futures):
                results.append(fut.result())

    # Stable index order: ml_share then run_index (not completion order).
    results.sort(key=lambda r: (float(r["ml_share"]), int(r["run_index"])))
    index = {
        "experiment_id": manifest.experiment_id,
        "base_seed": manifest.base_seed,
        "n_runs": manifest.n_runs,
        "ml_share_grid": list(manifest.ml_share_grid),
        "runs": results,
    }
    (output_dir / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return index
