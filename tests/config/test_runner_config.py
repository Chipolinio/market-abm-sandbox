# Назначение файла: проверить конфиги много-тикового прогона (Slice 004 §8).
# Базовая идея: SimulationRunConfig и ProductsBootstrapConfig валидируют вход.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_abm.config.runner import ProductsBootstrapConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig


def test_products_bootstrap_config_defaults() -> None:
    cfg = ProductsBootstrapConfig()
    assert cfg.delivery_days_min == pytest.approx(1.0)
    assert cfg.delivery_days_max == pytest.approx(7.0)
    assert cfg.rating_min == pytest.approx(3.2)
    assert cfg.rating_max == pytest.approx(5.0)
    assert cfg.rating_maximizer_boost == pytest.approx(0.35)


def test_products_bootstrap_rejects_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        ProductsBootstrapConfig(delivery_days_max=0.5, delivery_days_min=2.0)
    with pytest.raises(ValidationError):
        ProductsBootstrapConfig(rating_max=2.0, rating_min=4.0)


def test_simulation_run_config_defaults() -> None:
    cfg = SimulationRunConfig()
    assert cfg.seed is None
    assert isinstance(cfg.choice, ChoiceModelConfig)
    assert cfg.persistence.enabled is True
