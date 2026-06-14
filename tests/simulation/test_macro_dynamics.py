# Назначение файла: unit-тесты macro core (Slice 11.1, Spec 011 §13.1).
# Базовая идея: stress/expansion скаляры, impulse, advance, relax_multiplier — без buyers_df.
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.macro import CrisisScenarioConfig, MacroDynamicsConfig
from market_abm.config.shocks import ShockCatalogConfig
from market_abm.domain.constants import (
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_SELLER_ID,
    COL_UNIT_COST,
    COL_DEMAND_INDEX,
    COL_DELIVERY_DAYS,
    COL_RATING_VALUE,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.simulation.context import ShockCommand, SimulationContext, default_simulation_context
from market_abm.simulation.macro import (
    advance_macro_state,
    apply_demand_impulse,
    relax_multiplier_to_one,
)
from market_abm.simulation.shocks import apply_environment_shocks


def _fixed_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _macro_config(**overrides: object) -> MacroDynamicsConfig:
    return MacroDynamicsConfig.model_validate(overrides) if overrides else MacroDynamicsConfig()


def _ctx(
    *,
    stress: float = 0.0,
    expansion: float = 0.0,
    regime: MacroRegime = MacroRegime.NORMAL,
    tick_id: int = 0,
) -> SimulationContext:
    base = default_simulation_context(tick_id=tick_id)
    macro = MacroState(
        stress=stress,
        expansion=expansion,
        regime=regime,
        peak_stress=stress,
        peak_expansion=expansion,
    )
    return SimulationContext(
        tick_id=base.tick_id,
        active_shocks=base.active_shocks,
        platform_fee_rate=base.platform_fee_rate,
        macro=macro,
    )


def _crash_cmd(intensity: float = 1.0, duration_ticks: int = 10) -> ShockCommand:
    return ShockCommand(
        shock_type=ShockType.DEMAND_CRASH,
        intensity=intensity,
        duration_ticks=duration_ticks,
    )


def _boom_cmd(intensity: float = 1.0, duration_ticks: int = 10) -> ShockCommand:
    return ShockCommand(
        shock_type=ShockType.DEMAND_BOOM,
        intensity=intensity,
        duration_ticks=duration_ticks,
    )


def _buyers_df(budgets: list[float]) -> pl.DataFrame:
    n = len(budgets)
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: budgets,
            COL_BUDGET_BASELINE: budgets,
            COL_PURCHASE_FREQUENCY: [1.0] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BUDGET_BASELINE).cast(pl.Float32),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
    )


def _products_df(prices: list[float]) -> pl.DataFrame:
    n = len(prices)
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [50.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )


def test_impulse_increases_stress() -> None:
    ctx = _ctx(stress=0.0, expansion=0.2)
    config = _macro_config()
    rng = _fixed_rng()

    ctx2 = apply_demand_impulse(ctx, _crash_cmd(), config, rng)

    assert ctx2.macro.stress > ctx.macro.stress
    assert ctx2.macro.stress <= config.stress_cap
    assert ctx2.macro.expansion < ctx.macro.expansion
    assert ctx.macro.stress == 0.0


def test_advance_decays_stress() -> None:
    ctx = _ctx(stress=0.5, regime=MacroRegime.STRESS)
    config = _macro_config(decay_mode="persistence")
    rng = _fixed_rng()

    ctx_after = ctx
    for _ in range(10):
        ctx_after = advance_macro_state(ctx_after, config, rng)

    assert ctx_after.macro.stress < 0.5

    ctx_long = ctx
    for _ in range(50):
        ctx_long = advance_macro_state(ctx_long, config, rng)

    assert ctx_long.macro.stress < config.stress_exit_threshold
    assert ctx_long.macro.stress >= 0.0


def test_advance_stress_zero_stays_non_negative() -> None:
    ctx = _ctx(stress=0.0)
    config = _macro_config()
    rng = _fixed_rng()

    ctx2 = advance_macro_state(ctx, config, rng)

    assert ctx2.macro.stress == pytest.approx(0.0)


def test_regime_hysteresis() -> None:
    config = _macro_config()
    assert config.stress_enter_threshold > config.stress_exit_threshold

    rng = _fixed_rng()
    ctx = apply_demand_impulse(_ctx(), _crash_cmd(), config, rng)
    assert ctx.macro.stress >= config.stress_enter_threshold
    assert ctx.macro.regime == MacroRegime.STRESS

    regimes: list[MacroRegime] = [ctx.macro.regime]
    while ctx.macro.regime != MacroRegime.NORMAL and len(regimes) < 200:
        ctx = advance_macro_state(ctx, config, rng)
        regimes.append(ctx.macro.regime)

    assert MacroRegime.RECOVERY in regimes
    assert regimes.index(MacroRegime.RECOVERY) > regimes.index(MacroRegime.STRESS)
    assert ctx.macro.regime == MacroRegime.NORMAL
    assert ctx.macro.stress < config.recovery_done_threshold


def test_boom_expansion_decays_to_zero() -> None:
    config = _macro_config()
    rng = _fixed_rng()

    ctx = apply_demand_impulse(_ctx(), _boom_cmd(), config, rng)
    assert ctx.macro.expansion > 0.0

    prev_expansion = ctx.macro.expansion
    for _ in range(100):
        ctx = advance_macro_state(ctx, config, rng)
        assert ctx.macro.expansion <= prev_expansion + 1e-9
        prev_expansion = ctx.macro.expansion

    assert ctx.macro.expansion < config.recovery_done_threshold


def test_recovery_rate_pulls_mult_to_one() -> None:
    recovery_rate = 0.96
    m = 1.20
    prev = m
    for _ in range(150):
        m = relax_multiplier_to_one(m, recovery_rate)
        assert m >= 1.0
        assert m <= prev + 1e-12
        prev = m
    assert m == pytest.approx(1.0, abs=1e-3)

    m_crash = 0.70
    prev_crash = m_crash
    for _ in range(150):
        m_crash = relax_multiplier_to_one(m_crash, recovery_rate)
        assert m_crash <= 1.0
        assert m_crash >= prev_crash - 1e-12
        prev_crash = m_crash
    assert m_crash == pytest.approx(1.0, abs=1e-3)


def test_fixed_duration_legacy_matches_010() -> None:
    config = MacroDynamicsConfig(shock_mode="fixed_duration")
    assert config.shock_mode == "fixed_duration"

    buyers = _buyers_df([1000.0, 2000.0])
    products = _products_df([100.0, 200.0])
    ctx = SimulationContext(
        tick_id=0,
        active_shocks=(
            ActiveShock(
                shock_type=ShockType.DEMAND_CRASH,
                intensity=1.0,
                remaining_ticks=10,
                applied_at_tick=0,
            ),
        ),
        platform_fee_rate=0.15,
        macro=MacroState.empty(),
    )

    buyers_out, _ = apply_environment_shocks(
        buyers,
        products,
        ctx,
        ShockCatalogConfig(),
    )

    assert buyers_out[COL_BUDGET].to_list() == pytest.approx([700.0, 1400.0])
    assert buyers_out[COL_PURCHASE_FREQUENCY].to_list() == pytest.approx([0.7, 0.7])
    assert buyers_out[COL_BUDGET_BASELINE].to_list() == pytest.approx([1000.0, 2000.0])
    assert ctx.active_shocks[0].remaining_ticks == 10
