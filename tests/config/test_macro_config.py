# Назначение файла: валидация MacroDynamicsConfig и crisis presets (Slice 11.1).
from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_abm.config.macro import (
    BuyerEconomicBoundsConfig,
    CrisisScenarioConfig,
    MacroDynamicsConfig,
    SegmentElasticityConfig,
)


def test_macro_dynamics_defaults_match_spec() -> None:
    cfg = MacroDynamicsConfig()

    assert cfg.shock_mode == "stochastic_regime"
    assert cfg.persistence_stress == pytest.approx(0.96)
    assert cfg.persistence_expansion == pytest.approx(0.96)
    assert cfg.recovery_rate == pytest.approx(0.96)
    assert cfg.impulse_mean == pytest.approx(0.45)
    assert cfg.stress_cap == pytest.approx(1.2)
    assert cfg.expansion_cap == pytest.approx(0.8)
    assert cfg.stress_enter_threshold == pytest.approx(0.15)
    assert cfg.stress_exit_threshold == pytest.approx(0.12)
    assert cfg.stress_enter_threshold > cfg.stress_exit_threshold
    assert isinstance(cfg.segment_elasticity, SegmentElasticityConfig)
    assert isinstance(cfg.buyer_bounds, BuyerEconomicBoundsConfig)


def test_shock_mode_enum_values() -> None:
    stochastic = MacroDynamicsConfig(shock_mode="stochastic_regime")
    fixed = MacroDynamicsConfig(shock_mode="fixed_duration")
    assert stochastic.shock_mode == "stochastic_regime"
    assert fixed.shock_mode == "fixed_duration"


def test_crisis_scenario_presets() -> None:
    mild = CrisisScenarioConfig.mild()
    standard = CrisisScenarioConfig.standard()
    severe = CrisisScenarioConfig.severe()

    assert mild.impulse_mean == pytest.approx(0.25)
    assert mild.decay_rate == pytest.approx(0.06)
    assert mild.scar_cap == pytest.approx(0.08)

    assert standard.impulse_mean == pytest.approx(0.45)
    assert standard.decay_rate == pytest.approx(0.04)
    assert standard.scar_cap == pytest.approx(0.15)

    assert severe.impulse_mean == pytest.approx(0.65)
    assert severe.decay_rate == pytest.approx(0.03)
    assert severe.scar_cap == pytest.approx(0.25)


def test_buyer_bounds_nested_defaults() -> None:
    bounds = BuyerEconomicBoundsConfig()
    assert bounds.min_budget_fraction == pytest.approx(0.10)
    assert bounds.min_freq_fraction == pytest.approx(0.05)
    assert bounds.max_budget_mult == pytest.approx(1.35)
    assert bounds.min_budget_mult == pytest.approx(0.55)
    assert bounds.budget_floor_epsilon == pytest.approx(1.0)


def test_invalid_persistence_rejected() -> None:
    with pytest.raises(ValidationError):
        MacroDynamicsConfig(persistence_stress=1.5)
