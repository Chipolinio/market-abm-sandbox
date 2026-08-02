# Назначение файла: ML inference budget + rules fallback (Slice 11.5-T2, Spec 011 §5A.3).
from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import pytest

from market_abm.config.ml_repricing import CatBoostRepricingConfig
from market_abm.config.ml_runtime import MlRuntimeConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import COL_PRICE
from market_abm.simulation.step import step
from tests.simulation.test_ml_repricing_step import (
    _fake_registry,
    _rules_config,
    _setup,
)

pytestmark = pytest.mark.ml


def test_11_5_t2_slow_ml_predict_falls_back_to_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Mock slow predict → tick completes via rules path, not FAILED."""
    store, buyers, sellers, products = _setup(tmp_path, "slow_fallback")
    registry = _fake_registry(0.0)

    def _slow_predict(*args: object, **kwargs: object) -> np.ndarray:
        time.sleep(0.05)
        current = kwargs.get("current_prices")
        if current is None and len(args) > 2:
            current = args[2]
        n = len(np.asarray(current))
        return np.zeros(n, dtype=np.float32)

    monkeypatch.setattr(
        "market_abm.ml.catboost_repricing.predict_next_prices",
        _slow_predict,
    )

    products_before = products.clone()
    step_config = SimulationStepConfig(
        tick_id=11,
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market().model_copy(
            update={
                "mode": "hybrid",
                "warmup_ticks": 0,
                "ml": CatBoostRepricingConfig(),
            },
        ),
    )
    try:
        products_next, _tx, _state = step(
            buyers,
            sellers,
            products,
            step_config,
            ml_registry=registry,
            analytics_store=store,
            ml_runtime=MlRuntimeConfig(inference_timeout_ms=1.0),
        )
        products_rules, _, _ = step(
            buyers,
            sellers,
            products_before,
            _rules_config(tick_id=11).model_copy(
                update={
                    "repricing": RepricingConfig.default_market().model_copy(
                        update={"warmup_ticks": 0}
                    )
                }
            ),
        )
        assert products_next[COL_PRICE].to_list() == products_rules[COL_PRICE].to_list()
    finally:
        store.close()
