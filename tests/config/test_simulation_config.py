# Назначение файла: проверить конфиги шага симуляции для Slice 003.
# Базовая идея: входные параметры шага должны быть валидными и с понятными дефолтами.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig


def test_choice_model_config_has_expected_defaults() -> None:
    cfg = ChoiceModelConfig()
    assert cfg.engine == "choice_learn"
    assert cfg.outside_utility_bias == pytest.approx(-1.5)
    assert cfg.max_products_per_choice_set == 200
    assert cfg.buyers_batch_size == 5_000


def test_choice_model_config_rejects_invalid_choice_set_size() -> None:
    with pytest.raises(ValidationError):
        ChoiceModelConfig(max_products_per_choice_set=1)
    with pytest.raises(ValidationError):
        ChoiceModelConfig(max_products_per_choice_set=10_001)


def test_choice_model_config_rejects_invalid_batch_size() -> None:
    with pytest.raises(ValidationError):
        ChoiceModelConfig(buyers_batch_size=100)
    with pytest.raises(ValidationError):
        ChoiceModelConfig(buyers_batch_size=100_001)


def test_simulation_step_config_has_expected_defaults() -> None:
    cfg = SimulationStepConfig()
    assert cfg.tick_id == 0
    assert cfg.seed is None
    assert isinstance(cfg.choice, ChoiceModelConfig)
    assert isinstance(cfg.repricing, RepricingConfig)


def test_simulation_step_config_rejects_negative_tick() -> None:
    with pytest.raises(ValidationError):
        SimulationStepConfig(tick_id=-1)


def test_simulation_step_config_accepts_numpy_softmax_engine() -> None:
    cfg = SimulationStepConfig(
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        tick_id=7,
        seed=42,
    )
    assert cfg.choice.engine == "numpy_softmax"
    assert cfg.tick_id == 7
    assert cfg.seed == 42
