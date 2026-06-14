# Назначение файла: segment elasticity и income γ по PVD (Slice 11.3, Spec 011 §13.3).
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.macro import MacroDynamicsConfig, SegmentElasticityConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_IS_CHURNED,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PVD_SEGMENT,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.simulation.choice import (
    choose_listings_for_all_buyers,
    resolve_income_utility_gamma,
)
from market_abm.simulation.macro import apply_buyer_economic_state


def _fixed_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _stress_macro(stress: float) -> MacroState:
    return MacroState(
        stress=stress,
        regime=MacroRegime.STRESS,
        peak_stress=stress,
    )


def _segment_buyers(segment: str, *, budget: float = 1000.0, n: int = 50) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET_BASELINE: [budget] * n,
            COL_BUDGET_EFFECTIVE: [budget] * n,
            "budget": [budget] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
            COL_PVD_SEGMENT: [segment] * n,
            "purchase_frequency": [1.0] * n,
            "freq_baseline": [1.0] * n,
            "freq_effective": [1.0] * n,
            "scar_factor": [0.0] * n,
            "is_churned": [False] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET_BASELINE).cast(pl.Float32),
        pl.col(COL_BUDGET_EFFECTIVE).cast(pl.Float32),
        pl.col("budget").cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col(COL_PVD_SEGMENT).cast(pl.Categorical),
        pl.col("purchase_frequency").cast(pl.Float32),
        pl.col("freq_baseline").cast(pl.Float32),
        pl.col("freq_effective").cast(pl.Float32),
        pl.col("scar_factor").cast(pl.Float32),
        pl.col("is_churned").cast(pl.Boolean),
    )


def test_low_segment_budget_mult_lower_than_rich() -> None:
    config = MacroDynamicsConfig()
    macro = _stress_macro(0.50)

    rich = apply_buyer_economic_state(
        _segment_buyers("rich"), macro, config, _fixed_rng(1)
    )
    low = apply_buyer_economic_state(
        _segment_buyers("low"), macro, config, _fixed_rng(2)
    )

    rich_ratio = (
        rich[COL_BUDGET_EFFECTIVE] / rich[COL_BUDGET_BASELINE]
    ).mean()
    low_ratio = (
        low[COL_BUDGET_EFFECTIVE] / low[COL_BUDGET_BASELINE]
    ).mean()

    assert low_ratio < rich_ratio
    assert rich_ratio == pytest.approx(0.96, abs=0.02)
    assert low_ratio == pytest.approx(0.78, abs=0.03)


def test_low_churn_rate_higher_than_rich() -> None:
    config = MacroDynamicsConfig()
    macro = _stress_macro(1.0)
    n_each = 2_000

    rich = apply_buyer_economic_state(
        _segment_buyers("rich", n=n_each),
        macro,
        config,
        _fixed_rng(10),
    )
    low = apply_buyer_economic_state(
        _segment_buyers("low", n=n_each),
        macro,
        config,
        _fixed_rng(11),
    )

    rich_rate = float(rich[COL_IS_CHURNED].mean())
    low_rate = float(low[COL_IS_CHURNED].mean())

    assert low_rate > rich_rate
    assert rich_rate < 0.05
    assert low_rate > 0.05


def test_gamma_mult_low_increases_outside_vs_rich() -> None:
    products = pl.DataFrame(
        {
            COL_LISTING_ID: [0],
            COL_SELLER_ID: [0],
            "unit_cost": [10.0],
            COL_PRICE: [50.0],
            "demand_index": [1.0],
            COL_DELIVERY_DAYS: [3.0],
            COL_RATING_VALUE: [4.0],
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col("unit_cost").cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col("demand_index").cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )

    baseline = 200.0
    effective = 100.0
    rich = _segment_buyers("rich", budget=baseline, n=1).with_columns(
        pl.lit(effective, dtype=pl.Float32).alias(COL_BUDGET_EFFECTIVE),
    )
    low = _segment_buyers("low", budget=baseline, n=1).with_columns(
        pl.lit(effective, dtype=pl.Float32).alias(COL_BUDGET_EFFECTIVE),
    )

    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        outside_utility_bias=-13.0,
        income_utility_gamma=0.5,
        max_products_per_choice_set=10,
        buyers_batch_size=500,
    )
    elasticity = SegmentElasticityConfig()

    def conversion_rate(buyers: pl.DataFrame, *, seed: int) -> float:
        purchases = 0
        trials = 300
        for trial in range(trials):
            out = choose_listings_for_all_buyers(
                buyers,
                products,
                seed=seed + trial,
                config=cfg,
                segment_elasticity=elasticity,
            )
            if out[COL_LISTING_ID][0] is not None:
                purchases += 1
        return purchases / trials

    rich_rate = conversion_rate(rich, seed=100)
    low_rate = conversion_rate(low, seed=100)

    assert rich_rate > low_rate
    assert low_rate < 1.0


def test_resolve_income_gamma_scales_by_segment() -> None:
    cfg = ChoiceModelConfig(income_utility_gamma=0.35)
    elasticity = SegmentElasticityConfig()

    assert resolve_income_utility_gamma("rich", cfg, elasticity) == pytest.approx(0.21)
    assert resolve_income_utility_gamma("standard", cfg, elasticity) == pytest.approx(0.35)
    assert resolve_income_utility_gamma("low", cfg, elasticity) == pytest.approx(0.455)


def test_segment_elasticity_config_gamma_defaults_match_spec() -> None:
    seg = SegmentElasticityConfig()
    assert seg.gamma_mult_rich == pytest.approx(0.6)
    assert seg.gamma_mult_standard == pytest.approx(1.0)
    assert seg.gamma_mult_low == pytest.approx(1.3)
