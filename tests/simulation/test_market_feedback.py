# Назначение файла: market price feedback on macro stress (Slice 11.5-T1, Spec 011 §5.4).
from __future__ import annotations

import numpy as np

from market_abm.config.macro import MacroDynamicsConfig
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.simulation.context import SimulationContext
from market_abm.simulation.macro import advance_macro_state, apply_market_price_feedback


def _fixed_rng(seed: int = 42) -> np.random.Generator:
    return np.random.default_rng(seed)


def _stress_ctx(*, stress: float = 0.5, pre_crisis: float = 100.0) -> SimulationContext:
    macro = MacroState(
        stress=stress,
        expansion=0.0,
        regime=MacroRegime.STRESS,
        peak_stress=stress,
        peak_expansion=0.0,
    )
    return SimulationContext(
        tick_id=10,
        active_shocks=(),
        platform_fee_rate=0.0,
        macro=macro,
        pre_crisis_price_index=pre_crisis,
    )


def test_11_5_t1_price_drop_accelerates_stress_decay() -> None:
    """A/B feedback_gain 0 vs 0.15: price drop → faster stress decay."""
    ctx = _stress_ctx(stress=0.5, pre_crisis=100.0)
    current_median = 80.0  # 20% drop

    config_gain = MacroDynamicsConfig(feedback_gain=0.15, shock_mode="stochastic_regime")
    config_zero = config_gain.model_copy(update={"feedback_gain": 0.0})

    ctx_with_gain = apply_market_price_feedback(ctx, config_gain, current_median)
    ctx_no_gain = apply_market_price_feedback(ctx, config_zero, current_median)

    assert ctx_with_gain.macro.stress < ctx.macro.stress
    assert ctx_no_gain.macro.stress == ctx.macro.stress

    rng = _fixed_rng(7)
    ctx_adv_gain = advance_macro_state(ctx_with_gain, config_gain, rng)
    ctx_adv_zero = advance_macro_state(ctx_no_gain, config_zero, _fixed_rng(7))

    assert ctx_adv_gain.macro.stress < ctx_adv_zero.macro.stress
