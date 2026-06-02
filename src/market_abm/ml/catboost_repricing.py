# Назначение файла: обучение и I/O реестра CatBoost-моделей репрайсинга (Spec 005 §7).
# Базовая идея: модели — инфраструктура прогона (вне sellers_df); per-strategy регрессоры;
# fit-gate σ_min против дегенерации; save/load сверяют catboost_version + system_architecture.
from __future__ import annotations

import hashlib
import json
import platform
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import numpy as np
import polars as pl

from market_abm.config.ml_repricing import CatBoostRepricingConfig
from market_abm.domain.constants import COL_STRATEGY_TYPE

if TYPE_CHECKING:  # импорт только для типов, без runtime-зависимости от catboost
    from catboost import CatBoostRegressor

LABEL_COLUMN: Final[str] = "label_log_price_delta"
_REGISTRY_JSON: Final[str] = "registry.json"
_ML_INSTALL_HINT: Final[str] = 'CatBoost is required: pip install -e ".[ml]"'


@dataclass(frozen=True, slots=True)
class CatBoostModelRegistry:
    """Per-strategy регрессоры вне DataFrame (инфраструктурный артефакт прогона, §1.3)."""

    models: dict[str, "CatBoostRegressor"]
    feature_names: tuple[str, ...]
    train_config_hash: str


def _load_catboost() -> Any:
    """Ленивый импорт CatBoost; при отсутствии — ImportError с подсказкой об extra."""
    try:
        from catboost import CatBoostRegressor
    except ImportError as exc:  # pragma: no cover - проверяется только без extra
        raise ImportError(_ML_INSTALL_HINT) from exc
    return CatBoostRegressor


def _config_hash(config: CatBoostRepricingConfig) -> str:
    payload = config.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _system_architecture() -> str:
    return f"{sys.platform}-{platform.machine()}"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}"


def _catboost_version() -> str:
    import catboost

    return str(catboost.version.VERSION)


def fit_catboost_registry(
    training_df: pl.DataFrame,
    *,
    config: CatBoostRepricingConfig,
    min_rows_per_strategy: int = 10,
    random_seed: int = 0,
) -> CatBoostModelRegistry:
    """
    Обучает по одному CatBoostRegressor на strategy (Spec 005 §7.3).

    - X: float32 в порядке config.feature_spec.feature_names; y: label_log_price_delta;
    - sample_weight downweight нулей (мера D §4.3): zero → zero_label_downweight, иначе 1.0;
    - hold-out validation; std(y_hat_val) >= config.min_validation_pred_std иначе ValueError (gate §4.3.3);
    - train_config_hash = sha256(canonical config dump).
    """
    catboost_regressor = _load_catboost()
    from catboost import CatBoostError

    feature_names = tuple(config.feature_spec.feature_names)
    zero_weight = config.exploration.zero_label_downweight
    val_fraction = config.fit_validation_fraction
    min_pred_std = config.min_validation_pred_std

    models: dict[str, "CatBoostRegressor"] = {}
    for strategy in config.strategies:
        subset = training_df.filter(
            pl.col(COL_STRATEGY_TYPE).cast(pl.String) == strategy
        )
        if subset.height < min_rows_per_strategy:
            raise ValueError(
                f"insufficient training rows for strategy {strategy}: "
                f"{subset.height} < {min_rows_per_strategy}"
            )

        x = subset.select(list(feature_names)).to_numpy().astype(np.float32)
        y = subset[LABEL_COLUMN].to_numpy().astype(np.float64)
        weights = np.where(y == 0.0, zero_weight, 1.0).astype(np.float64)

        rng = np.random.default_rng(random_seed)
        perm = rng.permutation(subset.height)
        n_val = max(1, int(round(subset.height * val_fraction)))
        val_idx = perm[:n_val]
        train_idx = perm[n_val:]
        if train_idx.size == 0:
            raise ValueError(
                f"not enough rows to split train/validation for strategy {strategy}"
            )

        model = catboost_regressor(
            iterations=config.catboost_iterations,
            depth=config.catboost_depth,
            learning_rate=config.catboost_learning_rate,
            loss_function="RMSE",
            random_seed=random_seed,
            verbose=False,
            allow_writing_files=False,
        )
        try:
            model.fit(x[train_idx], y[train_idx], sample_weight=weights[train_idx])
        except CatBoostError as exc:
            # CatBoost отвергает вырожденную выборку (например, все таргеты равны) —
            # трактуем как дегенерацию модели (тот же контракт, что σ_min-gate, §4.3.3).
            raise ValueError(
                f"degenerate catboost model for strategy {strategy}: {exc}"
            ) from exc

        y_hat = np.asarray(model.predict(x[val_idx]), dtype=np.float64)
        pred_std = float(np.std(y_hat))
        if pred_std < min_pred_std:
            raise ValueError(
                f"degenerate catboost model for strategy {strategy}: "
                f"validation pred std {pred_std} < {min_pred_std}"
            )

        models[strategy] = model

    return CatBoostModelRegistry(
        models=models,
        feature_names=feature_names,
        train_config_hash=_config_hash(config),
    )


def save_registry(registry: CatBoostModelRegistry, *, run_root: Path) -> Path:
    """Пишет .cbm на каждую стратегию + registry.json с env-метаданными. Возвращает путь json."""
    ml_dir = Path(run_root) / "ml"
    ml_dir.mkdir(parents=True, exist_ok=True)

    for strategy, model in registry.models.items():
        model.save_model(str(ml_dir / f"catboost_{strategy}.cbm"), format="cbm")

    metadata = {
        "feature_names": list(registry.feature_names),
        "train_config_hash": registry.train_config_hash,
        "strategies": list(registry.models.keys()),
        "catboost_version": _catboost_version(),
        "python_version": _python_version(),
        "system_architecture": _system_architecture(),
    }
    registry_path = ml_dir / _REGISTRY_JSON
    registry_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return registry_path


def load_registry(
    registry_path: Path,
    *,
    strict_version: bool = True,
    strict_platform: bool = True,
) -> CatBoostModelRegistry:
    """Загружает реестр со сверкой catboost_version и system_architecture (Spec 005 §7.4)."""
    registry_path = Path(registry_path)
    if registry_path.is_dir():
        registry_path = registry_path / _REGISTRY_JSON
    metadata = json.loads(registry_path.read_text(encoding="utf-8"))

    _check_version(metadata.get("catboost_version", ""), strict_version)
    _check_python_version(metadata.get("python_version", ""))
    _check_platform(metadata.get("system_architecture", ""), strict_platform)

    catboost_regressor = _load_catboost()
    ml_dir = registry_path.parent
    models: dict[str, "CatBoostRegressor"] = {}
    for strategy in metadata["strategies"]:
        model = catboost_regressor()
        model.load_model(str(ml_dir / f"catboost_{strategy}.cbm"))
        models[strategy] = model

    return CatBoostModelRegistry(
        models=models,
        feature_names=tuple(metadata["feature_names"]),
        train_config_hash=metadata["train_config_hash"],
    )


def _major_minor(version: str) -> str:
    return ".".join(version.split(".")[:2])


def _check_version(saved_version: str, strict: bool) -> None:
    if not strict:
        return
    current = _catboost_version()
    if _major_minor(saved_version) != _major_minor(current):
        raise RuntimeError(
            f"CatBoost version mismatch: expected CatBoost {_major_minor(saved_version)}, "
            f"got {_major_minor(current)}"
        )


def _check_python_version(saved_python: str) -> None:
    current = _python_version()
    if saved_python and saved_python != current:
        warnings.warn(
            f"Python version mismatch: registry saved on {saved_python}, current {current}",
            stacklevel=2,
        )


def _check_platform(saved_arch: str, strict: bool) -> None:
    current = _system_architecture()
    if saved_arch == current:
        return
    message = (
        f"system_architecture mismatch: registry saved on '{saved_arch}', "
        f"current '{current}'. Cross-platform .cbm import risks Segfault/UB "
        f"in the CatBoost C++ core."
    )
    if strict:
        raise RuntimeError(message)
    warnings.warn(message, stacklevel=2)
