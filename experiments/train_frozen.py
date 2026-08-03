# Offline train → freeze CatBoost registry for Research Lab / paper grids.
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import polars as pl

from experiments.batch_runner import _research_seller_config
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.ml_repricing import BootstrapConfig, CatBoostRepricingConfig
from market_abm.config.repricing import ListingInitConfig
from market_abm.ml.bootstrap import collect_bootstrap_training_frame, run_bootstrap_simulation
from market_abm.ml.catboost_repricing import fit_catboost_registry, save_registry
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings

ProgressFn = Callable[[int, int, str], None]

DEFAULT_FROZEN_ROOT = Path("output") / "ml_frozen"
TRAIN_EXPERIMENT_ID = "ml-train"


def frozen_registry_status(frozen_root: Path | str = DEFAULT_FROZEN_ROOT) -> dict[str, Any]:
    """Describe whether a loadable frozen registry exists under frozen_root/ml/."""
    root = Path(frozen_root)
    registry_path = root / "ml" / "registry.json"
    meta: dict[str, Any] = {
        "present": False,
        "frozen_root": str(root.resolve()) if root.exists() else str(root),
        "registry_path": str(registry_path),
    }
    if not registry_path.is_file():
        return meta
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        meta["corrupt"] = True
        return meta
    meta["present"] = True
    meta["strategies"] = list(payload.get("strategies") or [])
    meta["train_config_hash"] = payload.get("train_config_hash")
    meta["catboost_version"] = payload.get("catboost_version")
    return meta


def train_frozen_registry(
    *,
    frozen_root: Path | str = DEFAULT_FROZEN_ROOT,
    work_dir: Path | str | None = None,
    n_runs: int = 3,
    n_ticks_per_run: int = 40,
    n_buyers: int = 80,
    n_sellers: int = 24,
    population_seed: int = 42,
    min_rows_per_strategy: int = 30,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    """
    Bootstrap rule-based runs → training frame → fit CatBoost → save under frozen_root/ml/.

    Progress: done in 0..n_runs+1 (bootstrap runs + fit/save).
    """
    frozen = Path(frozen_root)
    work = Path(work_dir) if work_dir is not None else frozen / "_bootstrap"
    work.mkdir(parents=True, exist_ok=True)
    frozen.mkdir(parents=True, exist_ok=True)

    total = int(n_runs) + 1
    if on_progress is not None:
        on_progress(0, total, "bootstrap_start")

    seed = int(population_seed)
    sellers = generate_sellers(_research_seller_config(n_sellers=int(n_sellers), seed=seed))
    buyers = generate_buyers(
        BuyerPopulationConfig.default_market(n_buyers=int(n_buyers), seed=seed)
    )
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=seed,
    )

    boot = BootstrapConfig(
        n_runs=int(n_runs),
        n_ticks_per_run=int(n_ticks_per_run),
        population_seed=seed,
        run_id_prefix="bootstrap",
        min_rows_per_strategy=int(min_rows_per_strategy),
    )

    # Run bootstrap one-by-one for progress (BootstrapConfig still drives n_ticks/seed).
    run_roots: list[Path] = []
    for i in range(boot.n_runs):
        single = boot.model_copy(
            update={"n_runs": 1, "run_id_prefix": f"bootstrap-{i}", "population_seed": seed + i}
        )
        roots = run_bootstrap_simulation(
            single,
            base_dir=work,
            buyers_df=buyers,
            sellers_df=sellers,
            listings_df=listings,
        )
        run_roots.extend(roots)
        if on_progress is not None:
            on_progress(i + 1, total, f"bootstrap_run_{i}")

    ml_config = CatBoostRepricingConfig()
    training = collect_bootstrap_training_frame(
        run_roots,
        sellers_df=sellers,
        spec=ml_config.feature_spec,
        config=ml_config,
        min_rows_per_strategy=boot.min_rows_per_strategy,
    )
    if training.height == 0:
        raise RuntimeError("bootstrap training frame is empty — cannot fit CatBoost")

    training = _apply_bootstrap_label_jitter(training, config=ml_config, seed=seed)

    registry = fit_catboost_registry(training, config=ml_config, random_seed=seed)
    registry_path = save_registry(registry, run_root=frozen)

    if on_progress is not None:
        on_progress(total, total, "fit_saved")

    status = frozen_registry_status(frozen)
    status["n_training_rows"] = int(training.height)
    status["registry_path"] = str(registry_path)
    status["n_bootstrap_runs"] = len(run_roots)
    return status


def _apply_bootstrap_label_jitter(
    training: pl.DataFrame,
    *,
    config: CatBoostRepricingConfig,
    seed: int,
) -> pl.DataFrame:
    """Spec 005 exploration: Gaussian jitter on a fraction of labels to avoid all-equal y."""
    from market_abm.ml.catboost_repricing import LABEL_COLUMN

    import numpy as np

    expl = config.exploration
    if not expl.enabled or expl.bootstrap_label_jitter_p <= 0.0:
        return training
    y = training[LABEL_COLUMN].to_numpy().astype(np.float64).copy()
    rng = np.random.default_rng(seed)
    mask = rng.random(y.shape[0]) < expl.bootstrap_label_jitter_p
    y[mask] = y[mask] + rng.normal(0.0, expl.bootstrap_label_jitter_sigma, size=int(mask.sum()))
    return training.with_columns(pl.Series(LABEL_COLUMN, y))
