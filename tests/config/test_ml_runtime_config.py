# Назначение файла: MlRuntimeConfig defaults (Slice 11.5, Spec 011 §5A.3).
from __future__ import annotations

from market_abm.config.ml_runtime import MlRuntimeConfig
from market_abm.config.runner import SimulationRunConfig


def test_ml_runtime_defaults() -> None:
    cfg = MlRuntimeConfig()
    assert cfg.inference_timeout_ms == 50.0
    assert cfg.fallback_to_rules_on_timeout is True
    assert cfg.max_listings_per_ml_tick == 5000


def test_simulation_run_config_includes_ml_runtime() -> None:
    run = SimulationRunConfig()
    assert run.ml_runtime.inference_timeout_ms == 50.0
