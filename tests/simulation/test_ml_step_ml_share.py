# Spec 015 slice 15.3 — step respects uses_ml mask + missing-registry fallback.
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from market_abm.config.ml_repricing import CatBoostRepricingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import COL_PRICE, COL_SELLER_ID, COL_USES_ML
from market_abm.simulation.ml_assignment import assign_ml_sellers
from market_abm.simulation.step import step
from tests.simulation.test_ml_repricing_step import (
    _fake_registry,
    _rules_config,
    _setup,
)

pytestmark = pytest.mark.ml


def _hybrid_config(*, tick_id: int, share: float, warmup: int = 0) -> SimulationStepConfig:
    return SimulationStepConfig(
        tick_id=tick_id,
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market().model_copy(
            update={
                "mode": "hybrid",
                "warmup_ticks": warmup,
                "ml_seller_share": share,
                "ml": CatBoostRepricingConfig(),
            },
        ),
    )


def test_15_3_t5_step_respects_mask(tmp_path: Path) -> None:
    """15.3-T5: ML predict only moves prices for uses_ml sellers."""
    store, buyers, sellers, products = _setup(tmp_path, "mask_share")
    n = sellers.height
    mid = n // 2
    uses = [i < mid for i in range(n)]
    sellers = sellers.with_columns(pl.Series(COL_USES_ML, uses, dtype=pl.Boolean))
    registry = _fake_registry(0.5)  # positive log-delta → prices up for ML path
    warnings: list[str] = []
    try:
        products_ml, _, _, _ = step(
            buyers,
            sellers,
            products,
            _hybrid_config(tick_id=20, share=0.5),
            ml_registry=registry,
            analytics_store=store,
            warnings_out=warnings,
        )
        products_rules, _, _, _ = step(
            buyers,
            sellers,
            products,
            _rules_config(tick_id=20).model_copy(
                update={
                    "repricing": RepricingConfig.default_market().model_copy(
                        update={"warmup_ticks": 0}
                    )
                }
            ),
        )
        ml_ids = set(sellers.filter(pl.col(COL_USES_ML))[COL_SELLER_ID].to_list())
        for row in products_ml.iter_rows(named=True):
            sid = int(row[COL_SELLER_ID])
            price_ml = float(row[COL_PRICE])
            price_rules = float(
                products_rules.filter(pl.col(COL_SELLER_ID) == sid)[COL_PRICE][0]
            )
            if sid in ml_ids:
                assert price_ml != price_rules
            else:
                assert price_ml == pytest.approx(price_rules)
    finally:
        store.close()


def test_15_3_t6_ml_missing_registry_fallback_rules(tmp_path: Path) -> None:
    """15.3-T6: share=1.0, registry=None → rules path + ml_fallback warning."""
    store, buyers, sellers, products = _setup(tmp_path, "fallback_share")
    sellers = assign_ml_sellers(sellers, share=1.0, seed=1)
    warnings: list[str] = []
    try:
        products_next, _, _, _ = step(
            buyers,
            sellers,
            products,
            _hybrid_config(tick_id=20, share=1.0),
            ml_registry=None,
            analytics_store=store,
            warnings_out=warnings,
        )
        products_rules, _, _, _ = step(
            buyers,
            sellers,
            products,
            _rules_config(tick_id=20).model_copy(
                update={
                    "repricing": RepricingConfig.default_market().model_copy(
                        update={"warmup_ticks": 0}
                    )
                }
            ),
        )
        assert products_next[COL_PRICE].to_list() == products_rules[COL_PRICE].to_list()
        assert any("ml_fallback" in w for w in warnings)
    finally:
        store.close()
