# Spec 015 §4.3 — headless batch runner (paired seeds, isolation, --jobs).
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import polars as pl

from experiments.manifest import ExperimentManifest
from experiments.seeds import seed_for_run
from market_abm.analytics.welfare import build_tick_metrics_row
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.common import CategoricalSpec
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import COL_BASE_COMMISSION, COL_USES_ML, PLATFORM_DEFAULTS
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.ml_assignment import assign_ml_sellers
from market_abm.simulation.runner import run_simulation, run_simulation_and_persist

# In-process isolation probe for tests / soft reset (Spec 015 §4.3.1).
_ISOLATION_DIRTY: bool = False


def _research_seller_config(*, n_sellers: int, seed: int) -> SellerPopulationConfig:
    """
    Research ablation seller mix: MaxProfit / MaxVolume only.

    RatingMaximizer is a hard no-op in apply_ml_repricing_tick (and rules). With the
    default mix, buyers often concentrate on a cheap RM listing → transaction metrics
    ignore ML share even when MaxProfit/MaxVolume shelf prices move.
    """
    base = SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
    return base.model_copy(
        update={
            "strategy_type": CategoricalSpec(
                levels=("MaxProfit", "MaxVolume"),
                probabilities=(0.5, 0.5),
            )
        }
    )

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
    sellers = generate_sellers(_research_seller_config(n_sellers=n_sellers, seed=seed))
    # Nested seller_id order: mid-shares expand ML set monotonically and include
    # low seller_ids (often the cheapest listing) — avoids smoke plateau where
    # permutation left the monopolist on rules until share=1.0.
    sellers = assign_ml_sellers(sellers, share=ml_share, seed=seed, order="seller_id")
    buyers = generate_buyers(
        BuyerPopulationConfig.default_market(n_buyers=n_buyers, seed=seed)
    )
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=seed,
    )

    ml_registry = None
    use_ml = ml_share > 0.0
    # Fair A/B: same warmup for rules baseline and hybrid (was 15 vs 0 → spurious gap).
    warmup_ticks = 0
    if use_ml:
        from market_abm.config.ml_repricing import CatBoostRepricingConfig
        from experiments.research_ml import resolve_research_ml_registry

        ml_registry, reg_warnings = resolve_research_ml_registry()
        warnings.extend(reg_warnings)
        repricing = RepricingConfig.default_market().model_copy(
            update={
                "mode": "hybrid",
                "ml_seller_share": ml_share,
                "ml": CatBoostRepricingConfig(),
                "warmup_ticks": warmup_ticks,
            }
        )
    else:
        repricing = RepricingConfig.default_market().model_copy(
            update={
                "ml_seller_share": 0.0,
                "warmup_ticks": warmup_ticks,
            }
        )

    # Milder than live (−100): extreme bias + small n → winner-take-all on one
    # listing, so mid-shares look bit-identical in GMV even when shelf prices move.
    persistence = PersistenceConfig(
        enabled=use_ml,
        base_dir=str(run_root),
        run_id="sim",
    )
    config = SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            outside_utility_bias=-70.0,
            outside_utility_bias_by_pvd_segment={
                "rich": -85.0,
                "standard": -70.0,
                "low": -55.0,
            },
            max_products_per_choice_set=min(50, max(n_sellers * 2, 8)),
            buyers_batch_size=max(n_buyers, 200),
        ),
        repricing=repricing,
        runtime_mode=runtime_mode,
        persistence=persistence,
    )

    metric_rows: list[dict[str, Any]] = []
    fee_rate = float(PLATFORM_DEFAULTS[COL_BASE_COMMISSION])
    sim_iter = (
        run_simulation_and_persist(
            buyers,
            sellers,
            listings,
            n_ticks=n_ticks,
            config=config,
            ml_registry=ml_registry,
            warnings_out=warnings,
        )
        if use_ml
        else run_simulation(
            buyers,
            sellers,
            listings,
            n_ticks=n_ticks,
            config=config,
            warnings_out=warnings,
        )
    )
    for tick_id, products_df, transactions_df in sim_iter:
        metric_rows.append(
            build_tick_metrics_row(
                tick_id=tick_id,
                transactions_df=transactions_df,
                buyers_df=buyers,
                products_df=products_df,
                platform_fee_rate=fee_rate,
            )
        )

    if use_ml and any("ml_fallback_rules: reason=missing_registry" in w for w in warnings):
        raise RuntimeError(
            "ML share > 0 but registry missing — ablation collapsed to rules; "
            "refusing to write identical-share artifacts"
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
        "n_ml_sellers": int(sellers.filter(pl.col(COL_USES_ML)).height)
        if COL_USES_ML in sellers.columns
        else 0,
    }
    _write_run_meta(run_root / "run_meta.json", meta)
    return meta


def run_experiment(
    manifest: ExperimentManifest,
    *,
    jobs: int | None = None,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    """
    Run full ml_share × seed grid. jobs=1 sequential; jobs>1 ProcessPoolExecutor.
    Returns index dict with experiment_id and runs[].
    on_progress(done, total, ml_share, run_index) optional callback after each run.
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

    total = len(tasks)
    results: list[dict[str, Any]] = []
    if n_jobs == 1:
        for i, task in enumerate(tasks, start=1):
            meta = _execute_one_run(task)
            results.append(meta)
            if on_progress is not None:
                on_progress(i, total, float(task["ml_share"]), int(task["run_index"]))
    else:
        with ProcessPoolExecutor(max_workers=n_jobs) as pool:
            future_map = {pool.submit(_execute_one_run, task): task for task in tasks}
            done_count = 0
            for fut in as_completed(future_map):
                task = future_map[fut]
                results.append(fut.result())
                done_count += 1
                if on_progress is not None:
                    on_progress(
                        done_count,
                        total,
                        float(task["ml_share"]),
                        int(task["run_index"]),
                    )

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
