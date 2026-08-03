# Spec 015 — research-batch ML registry resolution (frozen CatBoost or stub policy).
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from market_abm.config.ml_repricing import V1_FEATURE_NAMES
from market_abm.ml.catboost_repricing import (
    CatBoostModelRegistry,
    load_frozen_registry_for_run,
    load_registry,
)

# Env override: directory containing ml/registry.json, or the registry.json itself.
_ENV_REGISTRY: str = "MARKET_ABM_ML_REGISTRY"
# Default cached frozen root (run_root layout: <root>/ml/registry.json).
_ENV_FROZEN_DIR: str = "MARKET_ABM_ML_FROZEN_DIR"
_DEFAULT_FROZEN_ROOT: Path = Path("output") / "ml_frozen"

# Constant log-δ used when no trained CatBoost is available.
# Large enough that share ablation moves transaction metrics (not only shelf prices).
_STUB_LOG_DELTA: float = 0.08


class ConstantLogDeltaModel:
    """Minimal predict() stand-in for CatBoostRegressor (research stub only)."""

    def __init__(self, y_value: float) -> None:
        self.y_value = float(y_value)

    def predict(self, x: np.ndarray) -> np.ndarray:
        n = int(np.asarray(x).shape[0])
        return np.full(n, self.y_value, dtype=np.float64)


def build_research_stub_registry(
    *,
    log_delta: float = _STUB_LOG_DELTA,
) -> CatBoostModelRegistry:
    """
    Deterministic non-CatBoost policy: next ≈ price * exp(log_delta) + exploration.

    Covers all STRATEGY_TYPES (incl. RatingMaximizer). Production CatBoost registry
    historically omits RatingMaximizer → ML share can be invisible in tx metrics when
    buyers concentrate on the cheapest RM listing.
    """
    from market_abm.domain.constants import STRATEGY_TYPES

    return CatBoostModelRegistry(
        models={name: ConstantLogDeltaModel(log_delta) for name in STRATEGY_TYPES},
        feature_names=V1_FEATURE_NAMES,
        train_config_hash=f"sha256:research-stub-log-delta-{log_delta}-all-strats",
    )


def resolve_research_ml_registry() -> tuple[CatBoostModelRegistry, list[str]]:
    """
    Resolve ML registry for experiment ablation.

    Priority:
    1. MARKET_ABM_ML_REGISTRY → load frozen CatBoost
    2. output/ml_frozen/ml/registry.json if present
    3. research stub (constant log-delta) — metrics differ by share, not a trained model
    """
    warnings: list[str] = []
    env = os.environ.get(_ENV_REGISTRY, "").strip()
    if env:
        path = Path(env)
        registry = (
            load_registry(path, strict_version=False, strict_platform=False)
            if path.is_file() or (path / "registry.json").is_file()
            else load_frozen_registry_for_run(path)
        )
        if registry is None:
            raise FileNotFoundError(
                f"{_ENV_REGISTRY}={env!r} does not contain a loadable CatBoost registry"
            )
        warnings.append("ml_registry=frozen_env")
        return registry, warnings

    frozen_root = Path(os.environ.get(_ENV_FROZEN_DIR, "").strip() or _DEFAULT_FROZEN_ROOT)
    frozen = load_frozen_registry_for_run(frozen_root)
    if frozen is not None:
        warnings.append("ml_registry=frozen_default")
        return frozen, warnings

    warnings.append(
        f"ml_registry=research_stub_log_delta_{_STUB_LOG_DELTA}"
        f" (set {_ENV_REGISTRY} to use a trained CatBoost)"
    )
    return build_research_stub_registry(), warnings
