# Назначение файла: Pydantic-конфиги ML-репрайсинга (Spec 005 §8) — спецификация фич,
# гиперпараметры CatBoost, exploration и пороги drift. Только декларация, без runtime Polars.
# Базовая идея: FeatureSpec описывает СОСТАВ фич; CatBoostRepricingConfig — продуктовые пороги.
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Канонический порядок фич v1 (Spec 005 §4.2 / §5.1.3), без ключей listing_id/seller_id/strategy_type.
V1_FEATURE_NAMES: tuple[str, ...] = (
    "price",
    "unit_cost",
    "demand_index",
    "margin_floor",
    "capital",
    "lag_gmv_seller_1",
    "lag_tx_count_seller_1",
    "roll_mean_price_listing_5",
    "roll_tx_count_listing_5",
    "market_mean_price_lag_1",
    "competitor_mean_price_lag_1",
    "competitor_price_gap",
    "competitor_price_change_flag",
    "ticks_since_own_price_change",
    "tick_id",
)


class FeatureSpec(BaseModel):
    """Декларация состава фич: какие колонки собирать и базовый lookback."""

    model_config = {"frozen": True}

    feature_names: tuple[str, ...]
    lookback_ticks: int = Field(default=5, ge=1, le=50)
    fill_null: float = 0.0

    @classmethod
    def v1_default(cls) -> FeatureSpec:
        """Канонический набор фич v1 (15 признаков, порядок зафиксирован §4.2)."""
        return cls(feature_names=V1_FEATURE_NAMES)


class DriftMonitorConfig(BaseModel):
    """Пороги и окна мониторинга расслоения признаков (Spec 005 §10)."""

    model_config = {"frozen": True}

    enabled: bool = True
    check_every_n_ticks: int = Field(default=10, ge=1)
    reference_window_ticks: int = Field(default=20, ge=5)
    current_window_ticks: int = Field(default=20, ge=5)
    psi_n_bins: int = Field(default=10, ge=2, le=50)
    psi_threshold: float = Field(default=0.25, gt=0.0)
    js_threshold: float = Field(default=0.15, gt=0.0)
    continuous_min_unique: int = Field(default=11, ge=2)
    psi_bin_epsilon: float = Field(default=1e-4, gt=0.0)
    min_samples_for_drift: int = Field(default=500, ge=50)
    fail_on_drift: bool = False


class ExplorationConfig(BaseModel):
    """Каскад anti-stagnation на векторе цен и train-таргете (Spec 005 §4.5)."""

    model_config = {"frozen": True}

    enabled: bool = True
    mode: Literal["gaussian_log", "epsilon_greedy"] = "gaussian_log"
    gaussian_sigma: float = Field(default=0.02, gt=0.0)
    epsilon: float = Field(default=0.05, ge=0.0, le=1.0)
    epsilon_relative_step: float = Field(default=0.03, gt=0.0)
    bootstrap_label_jitter_p: float = Field(default=0.15, ge=0.0, le=1.0)
    bootstrap_label_jitter_sigma: float = Field(default=0.01, gt=0.0)
    zero_label_downweight: float = Field(default=0.25, ge=0.0, le=1.0)


class BootstrapConfig(BaseModel):
    """Параметры offline bootstrap-прогонов для сбора обучающей выборки (Spec 005 §6.2)."""

    model_config = {"frozen": True}

    n_runs: int = Field(default=3, ge=1)
    n_ticks_per_run: int = Field(default=40, ge=2)
    population_seed: int = 42
    run_id_prefix: str = "bootstrap"
    min_rows_per_strategy: int = Field(default=50, ge=0)


class CatBoostRepricingConfig(BaseModel):
    """Гиперпараметры CatBoost и продуктовые пороги детектора изменений (Spec 005 §8.1)."""

    model_config = {"frozen": True}

    strategies: tuple[str, ...] = ("MaxProfit", "MaxVolume")
    feature_spec: FeatureSpec = Field(default_factory=FeatureSpec.v1_default)
    competitor_change_eps: float = Field(default=0.005, gt=0.0)
    price_change_eps: float = Field(default=0.001, gt=0.0)
    max_price_multiplier: float = Field(default=3.0, gt=1.0)
    catboost_iterations: int = 100
    catboost_depth: int = 4
    catboost_learning_rate: float = 0.1
    fit_validation_fraction: float = Field(default=0.2, gt=0.0, lt=1.0)
    min_validation_pred_std: float = Field(default=1e-4, gt=0.0)
    exploration: ExplorationConfig = Field(default_factory=ExplorationConfig)
    drift: DriftMonitorConfig = Field(default_factory=DriftMonitorConfig)
