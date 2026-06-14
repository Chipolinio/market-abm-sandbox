# Назначение файла: Pydantic-конфиг макро-динамики кризиса (Slice 11.1, Spec 011 §8).
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BuyerEconomicBoundsConfig(BaseModel):
    """Anti-drift клипы для budget_effective / freq_effective (используется с 11.2)."""

    model_config = {"frozen": True}

    min_budget_fraction: float = Field(default=0.10, gt=0.0, le=1.0)
    min_freq_fraction: float = Field(default=0.05, gt=0.0, le=1.0)
    max_budget_mult: float = Field(default=1.35, ge=1.0, le=3.0)
    min_budget_mult: float = Field(default=0.55, gt=0.0, le=1.0)
    budget_floor_epsilon: float = Field(default=1.0, ge=0.0)


class SegmentElasticityConfig(BaseModel):
    """Сегментные коэффициенты PVD (полное использование — slice 11.3)."""

    model_config = {"frozen": True}

    alpha_budget_rich: float = Field(default=0.08, ge=0.0, le=1.0)
    alpha_budget_standard: float = Field(default=0.25, ge=0.0, le=1.0)
    alpha_budget_low: float = Field(default=0.45, ge=0.0, le=1.0)
    alpha_freq_rich: float = Field(default=0.05, ge=0.0, le=1.0)
    alpha_freq_standard: float = Field(default=0.20, ge=0.0, le=1.0)
    alpha_freq_low: float = Field(default=0.40, ge=0.0, le=1.0)
    alpha_budget_boom_rich: float = Field(default=0.04, ge=0.0, le=1.0)
    alpha_budget_boom_standard: float = Field(default=0.12, ge=0.0, le=1.0)
    alpha_budget_boom_low: float = Field(default=0.22, ge=0.0, le=1.0)
    alpha_freq_boom_rich: float = Field(default=0.03, ge=0.0, le=1.0)
    alpha_freq_boom_standard: float = Field(default=0.10, ge=0.0, le=1.0)
    alpha_freq_boom_low: float = Field(default=0.20, ge=0.0, le=1.0)
    k_scar_rich: float = Field(default=0.002, ge=0.0, le=1.0)
    k_scar_standard: float = Field(default=0.004, ge=0.0, le=1.0)
    k_scar_low: float = Field(default=0.008, ge=0.0, le=1.0)
    p_churn_rich: float = Field(default=0.01, ge=0.0, le=1.0)
    p_churn_standard: float = Field(default=0.05, ge=0.0, le=1.0)
    p_churn_low: float = Field(default=0.12, ge=0.0, le=1.0)
    churn_stress_threshold_rich: float = Field(default=0.50, ge=0.0, le=2.0)
    churn_stress_threshold_standard: float = Field(default=0.45, ge=0.0, le=2.0)
    churn_stress_threshold_low: float = Field(default=0.40, ge=0.0, le=2.0)
    gamma_mult_rich: float = Field(default=0.6, gt=0.0, le=5.0)
    gamma_mult_standard: float = Field(default=1.0, gt=0.0, le=5.0)
    gamma_mult_low: float = Field(default=1.3, gt=0.0, le=5.0)

    def gamma_mult_for(self, pvd_segment: str) -> float:
        """Множитель γ для income utility по PVD-сегменту (Spec 011 §4.2)."""
        return {
            "rich": self.gamma_mult_rich,
            "standard": self.gamma_mult_standard,
            "low": self.gamma_mult_low,
        }.get(pvd_segment, 1.0)


class MacroDynamicsConfig(BaseModel):
    """Параметры stochastic macro regime и legacy fixed_duration gate."""

    model_config = {"frozen": True}

    shock_mode: Literal["stochastic_regime", "fixed_duration"] = "stochastic_regime"
    impulse_mean: float = Field(default=0.45, ge=0.0, le=2.0)
    impulse_sigma: float = Field(default=0.08, ge=0.0, le=1.0)
    boom_impulse_mean: float = Field(default=0.35, ge=0.0, le=2.0)
    boom_impulse_sigma: float = Field(default=0.06, ge=0.0, le=1.0)
    persistence_stress: float = Field(default=0.96, gt=0.0, lt=1.0)
    persistence_expansion: float = Field(default=0.96, gt=0.0, lt=1.0)
    recovery_rate: float = Field(default=0.96, gt=0.0, lt=1.0)
    decay_rate: float = Field(default=0.04, ge=0.0, le=1.0)
    decay_exponent: float = Field(default=1.15, ge=1.0, le=3.0)
    decay_mode: Literal["persistence", "nonlinear_drain"] = "persistence"
    stress_noise_sigma: float = Field(default=0.01, ge=0.0, le=0.5)
    stress_cap: float = Field(default=1.2, gt=0.0, le=5.0)
    expansion_cap: float = Field(default=0.8, gt=0.0, le=5.0)
    stress_enter_threshold: float = Field(default=0.15, ge=0.0, le=2.0)
    stress_exit_threshold: float = Field(default=0.12, ge=0.0, le=2.0)
    expansion_enter_threshold: float = Field(default=0.12, ge=0.0, le=2.0)
    expansion_exit_threshold: float = Field(default=0.10, ge=0.0, le=2.0)
    recovery_done_threshold: float = Field(default=0.05, ge=0.0, le=1.0)
    expansion_bleed_on_crash: float = Field(default=0.15, ge=0.0, le=2.0)
    stress_bleed_on_boom: float = Field(default=0.10, ge=0.0, le=2.0)
    scar_threshold: float = Field(default=0.35, ge=0.0, le=2.0)
    scar_cap: float = Field(default=0.25, ge=0.0, le=1.0)
    feedback_gain: float = Field(default=0.15, ge=0.0, le=2.0)
    beta_budget: float = Field(default=1.0, ge=0.5, le=3.0)
    beta_freq: float = Field(default=1.2, ge=0.5, le=3.0)
    beta_boom: float = Field(default=1.0, ge=0.5, le=3.0)
    freq_mult_cap: float = Field(default=1.0, gt=0.0, le=2.0)
    segment_elasticity: SegmentElasticityConfig = Field(default_factory=SegmentElasticityConfig)
    buyer_bounds: BuyerEconomicBoundsConfig = Field(default_factory=BuyerEconomicBoundsConfig)


class CrisisScenarioConfig(BaseModel):
    """Пресет сценария кризиса для UI / POST /shock."""

    model_config = {"frozen": True}

    name: Literal["mild", "standard", "severe"]
    impulse_mean: float = Field(ge=0.0, le=2.0)
    impulse_sigma: float = Field(default=0.08, ge=0.0, le=1.0)
    boom_impulse_mean: float = Field(default=0.35, ge=0.0, le=2.0)
    boom_impulse_sigma: float = Field(default=0.06, ge=0.0, le=1.0)
    decay_rate: float = Field(ge=0.0, le=1.0)
    scar_cap: float = Field(ge=0.0, le=1.0)

    @classmethod
    def mild(cls) -> CrisisScenarioConfig:
        return cls(
            name="mild",
            impulse_mean=0.25,
            decay_rate=0.06,
            scar_cap=0.08,
        )

    @classmethod
    def standard(cls) -> CrisisScenarioConfig:
        return cls(
            name="standard",
            impulse_mean=0.45,
            decay_rate=0.04,
            scar_cap=0.15,
        )

    @classmethod
    def severe(cls) -> CrisisScenarioConfig:
        return cls(
            name="severe",
            impulse_mean=0.65,
            decay_rate=0.03,
            scar_cap=0.25,
        )
