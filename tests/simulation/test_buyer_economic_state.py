# Назначение файла: unit-тесты buyer economic state (Slice 11.2, Spec 011 §13.2).
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.macro import MacroDynamicsConfig
from market_abm.domain.constants import (
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_BUYER_ID,
    COL_FREQ_BASELINE,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_PVD_SEGMENT,
    COL_SCAR_FACTOR,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.domain.shocks import ShockType
from market_abm.population.buyers import generate_buyers
from market_abm.simulation.context import ShockCommand, default_simulation_context
from market_abm.simulation.macro import (
    apply_buyer_economic_state,
    apply_demand_impulse,
)


def _fixed_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _macro_config(**overrides: object) -> MacroDynamicsConfig:
    return MacroDynamicsConfig.model_validate(overrides) if overrides else MacroDynamicsConfig()


def _stress_macro(stress: float) -> MacroState:
    return MacroState(
        stress=stress,
        regime=MacroRegime.STRESS,
        peak_stress=stress,
    )


def _sample_buyers(n: int = 200, seed: int = 7) -> pl.DataFrame:
    return generate_buyers(BuyerPopulationConfig.default_market(n_buyers=n, seed=seed))


def test_scar_increases_in_stress() -> None:
    config = _macro_config()
    macro = _stress_macro(0.50)
    buyers = _sample_buyers()

    out = apply_buyer_economic_state(buyers, macro, config, _fixed_rng())
    for _ in range(20):
        out = apply_buyer_economic_state(out, macro, config, _fixed_rng(99))

    assert out[COL_SCAR_FACTOR].max() > 0.0


def test_churn_irreversible() -> None:
    config = MacroDynamicsConfig(
        segment_elasticity=MacroDynamicsConfig().segment_elasticity.model_copy(
            update={
                "p_churn_low": 1.0,
                "churn_stress_threshold_low": 0.10,
            }
        ),
    )
    buyers = _sample_buyers(n=500, seed=11).with_columns(
        pl.lit("low").cast(pl.Categorical).alias(COL_PVD_SEGMENT),
    )
    macro = _stress_macro(1.0)
    rng = _fixed_rng(123)

    churned = apply_buyer_economic_state(buyers, macro, config, rng)
    assert churned[COL_IS_CHURNED].sum() > 0

    churned_ids = churned.filter(pl.col(COL_IS_CHURNED))[COL_BUYER_ID].to_list()
    again = apply_buyer_economic_state(churned, macro, config, _fixed_rng(456))
    subset = again.filter(pl.col(COL_BUYER_ID).is_in(churned_ids))

    assert subset[COL_IS_CHURNED].all()
    assert subset[COL_FREQ_EFFECTIVE].max() == pytest.approx(0.0)


def test_effective_budget_below_baseline_under_stress() -> None:
    config = _macro_config()
    macro = _stress_macro(0.55)
    buyers = _sample_buyers()

    out = apply_buyer_economic_state(buyers, macro, config, _fixed_rng())

    assert out[COL_BUDGET_EFFECTIVE].mean() < out[COL_BUDGET_BASELINE].mean()


def test_freq_recovers_slower_than_budget() -> None:
    config = _macro_config()
    macro = _stress_macro(0.50)
    buyers = _sample_buyers()

    out = apply_buyer_economic_state(buyers, macro, config, _fixed_rng())
    baseline = out[COL_BUDGET_BASELINE].to_numpy()
    freq_base = out[COL_FREQ_BASELINE].to_numpy()
    budget_ratio = out[COL_BUDGET_EFFECTIVE].to_numpy() / baseline
    freq_ratio = out[COL_FREQ_EFFECTIVE].to_numpy() / freq_base

    assert float(freq_ratio.mean()) > float(budget_ratio.mean())


def test_long_run_budget_respects_min_fraction() -> None:
    config = _macro_config()
    macro = _stress_macro(0.30)
    buyers = _sample_buyers(n=100, seed=3)
    baseline = buyers[COL_BUDGET_BASELINE].to_numpy()
    min_fraction = config.buyer_bounds.min_budget_fraction

    out = buyers
    for tick in range(500):
        out = apply_buyer_economic_state(
            out,
            macro,
            config,
            _fixed_rng(tick),
        )

    effective = out[COL_BUDGET_EFFECTIVE].to_numpy()
    assert np.all(effective >= baseline * min_fraction - 1e-4)


def test_stacked_shocks_hit_floor_not_zero() -> None:
    config = _macro_config(shock_mode="stochastic_regime", impulse_sigma=0.0)
    ctx = default_simulation_context()
    buyers = _sample_buyers(n=300, seed=5)
    baseline_mean = float(buyers[COL_BUDGET_BASELINE].mean())
    floor = baseline_mean * config.buyer_bounds.min_budget_fraction

    out = buyers
    for i in range(8):
        ctx = apply_demand_impulse(
            ctx,
            ShockCommand(
                shock_type=ShockType.DEMAND_CRASH,
                intensity=1.0,
                duration_ticks=10,
            ),
            config,
            _fixed_rng(i),
        )
        out = apply_buyer_economic_state(out, ctx.macro, config, _fixed_rng(i + 100))

    assert float(out[COL_BUDGET_EFFECTIVE].mean()) >= floor
