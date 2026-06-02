# Назначение файла: RED-тесты слайса 5.3 — fit/registry I/O CatBoost (Spec 005 §7, §12.4).
# Базовая идея: per-strategy модели вне таблиц; save/load с env-метаданными; fit-gate σ_min;
# сверка catboost_version и system_architecture на load (cross-platform → RuntimeError).
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from market_abm.config.ml_repricing import (
    CatBoostRepricingConfig,
    V1_FEATURE_NAMES,
)
from market_abm.domain.constants import COL_STRATEGY_TYPE

# --- SUT (ещё не существует → RED на импорте) ---
from market_abm.ml.catboost_repricing import (
    CatBoostModelRegistry,
    fit_catboost_registry,
    load_registry,
    save_registry,
)

pytestmark = pytest.mark.ml

LABEL_COL = "label_log_price_delta"


def _training_df(
    *, n_per_strategy: int = 80, seed: int = 0, degenerate: bool = False
) -> pl.DataFrame:
    rng = np.random.default_rng(seed)
    parts: list[pl.DataFrame] = []
    for strategy in ("MaxProfit", "MaxVolume"):
        n = n_per_strategy
        data: dict[str, object] = {}
        for name in V1_FEATURE_NAMES:
            data[name] = rng.normal(0.0, 1.0, n)
        if degenerate:
            label = np.zeros(n)
        else:
            label = 0.15 * np.asarray(data["competitor_price_gap"]) + rng.normal(
                0.0, 0.05, n
            )
        data[LABEL_COL] = label
        data[COL_STRATEGY_TYPE] = [strategy] * n
        parts.append(pl.DataFrame(data))
    return pl.concat(parts).with_columns(
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical)
    )


def _x_sample(training_df: pl.DataFrame, feature_names: tuple[str, ...]) -> np.ndarray:
    return training_df.head(5).select(list(feature_names)).to_numpy().astype(np.float32)


# --- 5.3-T1 ---


def test_fit_produces_two_models() -> None:
    registry = fit_catboost_registry(
        _training_df(), config=CatBoostRepricingConfig()
    )
    assert isinstance(registry, CatBoostModelRegistry)
    assert set(registry.models.keys()) == {"MaxProfit", "MaxVolume"}
    assert tuple(registry.feature_names) == V1_FEATURE_NAMES


# --- 5.3-T2 ---


def test_save_load_registry_roundtrip(tmp_path: Path) -> None:
    df = _training_df()
    config = CatBoostRepricingConfig()
    registry = fit_catboost_registry(df, config=config)
    x = _x_sample(df, registry.feature_names)
    before = registry.models["MaxProfit"].predict(x)

    registry_path = save_registry(registry, run_root=tmp_path)
    loaded = load_registry(registry_path)
    after = loaded.models["MaxProfit"].predict(x)

    assert np.allclose(before, after, atol=1e-6)
    assert loaded.train_config_hash == registry.train_config_hash


# --- 5.3-T3 ---


def test_train_config_hash_stable() -> None:
    config = CatBoostRepricingConfig()
    r1 = fit_catboost_registry(_training_df(seed=1), config=config)
    r2 = fit_catboost_registry(_training_df(seed=2), config=config)
    assert r1.train_config_hash == r2.train_config_hash
    assert r1.train_config_hash.startswith("sha256:")


# --- 5.3-T4 ---


def test_insufficient_rows_raises() -> None:
    df = _training_df(n_per_strategy=5)
    with pytest.raises(ValueError):
        fit_catboost_registry(
            df, config=CatBoostRepricingConfig(), min_rows_per_strategy=100
        )


# --- 5.3-T5 ---


def test_load_registry_version_mismatch_raises(tmp_path: Path) -> None:
    registry = fit_catboost_registry(_training_df(), config=CatBoostRepricingConfig())
    registry_path = save_registry(registry, run_root=tmp_path)

    meta = json.loads(registry_path.read_text(encoding="utf-8"))
    meta["catboost_version"] = "0.1.0"
    registry_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_registry(registry_path)


# --- 5.3-T6 ---


def test_save_registry_writes_env_metadata(tmp_path: Path) -> None:
    registry = fit_catboost_registry(_training_df(), config=CatBoostRepricingConfig())
    registry_path = save_registry(registry, run_root=tmp_path)
    meta = json.loads(registry_path.read_text(encoding="utf-8"))
    for key in (
        "feature_names",
        "train_config_hash",
        "strategies",
        "catboost_version",
        "python_version",
        "system_architecture",
    ):
        assert key in meta
    assert meta["strategies"] == ["MaxProfit", "MaxVolume"]


# --- 5.3-T7 ---


def test_fit_rejects_degenerate_validation_std() -> None:
    df = _training_df(degenerate=True)
    with pytest.raises(ValueError):
        fit_catboost_registry(df, config=CatBoostRepricingConfig())


# --- 5.3-T8 ---


def test_load_registry_cross_platform_raises(tmp_path: Path) -> None:
    registry = fit_catboost_registry(_training_df(), config=CatBoostRepricingConfig())
    registry_path = save_registry(registry, run_root=tmp_path)

    meta = json.loads(registry_path.read_text(encoding="utf-8"))
    meta["system_architecture"] = "totally-other-arch"
    registry_path.write_text(json.dumps(meta), encoding="utf-8")

    with pytest.raises(RuntimeError):
        load_registry(registry_path)
    # strict_platform=False → только warning, не падает
    loaded = load_registry(registry_path, strict_platform=False)
    assert set(loaded.models.keys()) == {"MaxProfit", "MaxVolume"}
