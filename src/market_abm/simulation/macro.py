# Назначение файла: чистые функции макро-динамики (Slice 11.1, Spec 011 §3, §9.1).
# Базовая идея: impulse + advance на MacroState в SimulationContext, без buyers_df.
from __future__ import annotations

import numpy as np
from dataclasses import replace

from market_abm.config.macro import CrisisScenarioConfig, MacroDynamicsConfig
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand, SimulationContext


def relax_multiplier_to_one(multiplier: float, recovery_rate: float) -> float:
    """
    Затухание мультипликатора к 1.0: m' = 1 + (m - 1) * recovery_rate.
    При boom (m > 1) — снижение; при crash (m < 1) — рост.
    """
    return 1.0 + (multiplier - 1.0) * recovery_rate


def _clip_stress(value: float, cap: float) -> float:
    return float(min(max(value, 0.0), cap))


def _clip_expansion(value: float, cap: float) -> float:
    return float(min(max(value, 0.0), cap))


def _resolve_crash_impulse(
    cmd: ShockCommand,
    config: MacroDynamicsConfig,
    scenario: CrisisScenarioConfig | None,
    rng: np.random.Generator,
) -> float:
    mean = scenario.impulse_mean if scenario is not None else config.impulse_mean
    sigma = scenario.impulse_sigma if scenario is not None else config.impulse_sigma
    noise = float(rng.normal(0.0, sigma))
    return (mean + noise) * cmd.intensity


def _resolve_boom_impulse(
    cmd: ShockCommand,
    config: MacroDynamicsConfig,
    scenario: CrisisScenarioConfig | None,
    rng: np.random.Generator,
) -> float:
    mean = scenario.boom_impulse_mean if scenario is not None else config.boom_impulse_mean
    sigma = scenario.boom_impulse_sigma if scenario is not None else config.boom_impulse_sigma
    noise = float(rng.normal(0.0, sigma))
    return (mean + noise) * cmd.intensity


def _apply_crash_impulse(
    macro: MacroState,
    impulse: float,
    config: MacroDynamicsConfig,
) -> MacroState:
    stress = _clip_stress(macro.stress + impulse, config.stress_cap)
    expansion = max(macro.expansion - config.expansion_bleed_on_crash, 0.0)
    regime = (
        MacroRegime.STRESS
        if stress >= config.stress_enter_threshold
        else macro.regime
    )
    new_episode = macro.regime == MacroRegime.NORMAL and regime == MacroRegime.STRESS
    return MacroState(
        stress=stress,
        expansion=expansion,
        regime=regime,
        peak_stress=max(macro.peak_stress, stress),
        peak_expansion=max(macro.peak_expansion, expansion),
        episode_id=macro.episode_id + (1 if new_episode else 0),
        ticks_in_episode=0 if new_episode else macro.ticks_in_episode,
    )


def _apply_boom_impulse(
    macro: MacroState,
    impulse: float,
    config: MacroDynamicsConfig,
) -> MacroState:
    expansion = _clip_expansion(macro.expansion + impulse, config.expansion_cap)
    stress = max(macro.stress - config.stress_bleed_on_boom, 0.0)
    regime = (
        MacroRegime.EXPANSION
        if expansion >= config.expansion_enter_threshold
        else macro.regime
    )
    new_episode = macro.regime == MacroRegime.NORMAL and regime == MacroRegime.EXPANSION
    return MacroState(
        stress=stress,
        expansion=expansion,
        regime=regime,
        peak_stress=max(macro.peak_stress, stress),
        peak_expansion=max(macro.peak_expansion, expansion),
        episode_id=macro.episode_id + (1 if new_episode else 0),
        ticks_in_episode=0 if new_episode else macro.ticks_in_episode,
    )


def apply_demand_impulse(
    ctx: SimulationContext,
    cmd: ShockCommand,
    config: MacroDynamicsConfig,
    rng: np.random.Generator,
    *,
    scenario: CrisisScenarioConfig | None = None,
) -> SimulationContext:
    """Стохастический импульс DEMAND_CRASH / DEMAND_BOOM в macro state."""
    macro = ctx.macro

    if cmd.shock_type == ShockType.DEMAND_CRASH:
        impulse = _resolve_crash_impulse(cmd, config, scenario, rng)
        macro = _apply_crash_impulse(macro, impulse, config)
    elif cmd.shock_type == ShockType.DEMAND_BOOM:
        impulse = _resolve_boom_impulse(cmd, config, scenario, rng)
        macro = _apply_boom_impulse(macro, impulse, config)
    else:
        return ctx

    return replace(ctx, macro=macro)


def _decay_stress(macro: MacroState, config: MacroDynamicsConfig) -> float:
    if config.decay_mode == "nonlinear_drain":
        drained = macro.stress - config.decay_rate * (macro.stress ** config.decay_exponent)
        return max(drained, 0.0)
    return macro.stress * config.persistence_stress


def _decay_expansion(macro: MacroState, config: MacroDynamicsConfig) -> float:
    if config.decay_mode == "nonlinear_drain":
        drained = macro.expansion - config.decay_rate * (macro.expansion ** config.decay_exponent)
        return max(drained, 0.0)
    return macro.expansion * config.persistence_expansion


def _update_regime(macro: MacroState, config: MacroDynamicsConfig) -> MacroRegime:
    regime = macro.regime

    if regime == MacroRegime.STRESS and macro.stress < config.stress_exit_threshold:
        regime = MacroRegime.RECOVERY
    elif regime == MacroRegime.EXPANSION and macro.expansion < config.expansion_exit_threshold:
        regime = MacroRegime.RECOVERY
    elif regime == MacroRegime.RECOVERY:
        if (
            macro.stress < config.recovery_done_threshold
            and macro.expansion < config.recovery_done_threshold
        ):
            regime = MacroRegime.NORMAL

    return regime


def advance_macro_state(
    ctx: SimulationContext,
    config: MacroDynamicsConfig,
    rng: np.random.Generator,
) -> SimulationContext:
    """Затухание stress/expansion и переходы regime каждый тик."""
    macro = ctx.macro

    stress = _clip_stress(_decay_stress(macro, config), config.stress_cap)
    expansion = _clip_expansion(_decay_expansion(macro, config), config.expansion_cap)

    if macro.regime == MacroRegime.STRESS and config.stress_noise_sigma > 0.0:
        stress = _clip_stress(
            stress + float(rng.normal(0.0, config.stress_noise_sigma)),
            config.stress_cap,
        )

    regime = _update_regime(
        MacroState(
            stress=stress,
            expansion=expansion,
            regime=macro.regime,
            peak_stress=macro.peak_stress,
            peak_expansion=macro.peak_expansion,
            episode_id=macro.episode_id,
            ticks_in_episode=macro.ticks_in_episode,
        ),
        config,
    )

    macro_next = MacroState(
        stress=stress,
        expansion=expansion,
        regime=regime,
        peak_stress=macro.peak_stress,
        peak_expansion=macro.peak_expansion,
        episode_id=macro.episode_id,
        ticks_in_episode=macro.ticks_in_episode + 1,
    )
    return replace(ctx, macro=macro_next)
