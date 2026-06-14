# Назначение файла: чистые функции макро-динамики (Slice 11.1–11.2, Spec 011 §3, §9.1).
# Базовая идея: impulse + advance на MacroState; buyer economic state — новый DataFrame.
from __future__ import annotations

import numpy as np
import polars as pl
from dataclasses import replace

from market_abm.config.macro import CrisisScenarioConfig, MacroDynamicsConfig, SegmentElasticityConfig
from market_abm.domain.constants import (
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_FREQ_BASELINE,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_PRICE,
    COL_PVD_SEGMENT,
    COL_SCAR_FACTOR,
)
from market_abm.domain.macro import DemandImpulseLog, MacroRegime, MacroState
from market_abm.domain.shocks import ShockType
from market_abm.simulation.buyers_baseline import ensure_buyer_economic_columns
from market_abm.simulation.context import ShockCommand, SimulationContext

_MACRO_SALT = 0x110011


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


def median_listing_price(products_df: pl.DataFrame) -> float:
    """Медиана listing price для market feedback (Spec 011 §5.4)."""
    if products_df.height == 0:
        return 0.0
    return float(products_df[COL_PRICE].median())


def apply_market_price_feedback(
    ctx: SimulationContext,
    config: MacroDynamicsConfig,
    current_median_p50: float,
) -> SimulationContext:
    """
    Ускоряет decay stress при падении median price vs pre-crisis snapshot.
    price_response = (pre - current) / pre; stress -= gain * max(0, response) * stress.
    """
    if config.feedback_gain <= 0.0:
        return ctx
    baseline = ctx.pre_crisis_price_index
    if baseline is None or baseline <= 0.0 or current_median_p50 <= 0.0:
        return ctx

    price_response = (baseline - current_median_p50) / baseline
    if price_response <= 0.0:
        return ctx

    macro = ctx.macro
    if macro.stress <= 0.0:
        return ctx

    stress = max(
        macro.stress - config.feedback_gain * price_response * macro.stress,
        0.0,
    )
    macro_next = MacroState(
        stress=stress,
        expansion=macro.expansion,
        regime=macro.regime,
        peak_stress=macro.peak_stress,
        peak_expansion=macro.peak_expansion,
        episode_id=macro.episode_id,
        ticks_in_episode=macro.ticks_in_episode,
    )
    return replace(ctx, macro=macro_next)


def update_pre_crisis_price_index(
    ctx: SimulationContext,
    *,
    previous_regime: MacroRegime,
    current_median_p50: float,
) -> SimulationContext:
    """Фиксирует pre-crisis median при входе в STRESS."""
    if (
        ctx.macro.regime == MacroRegime.STRESS
        and previous_regime != MacroRegime.STRESS
        and current_median_p50 > 0.0
    ):
        return replace(ctx, pre_crisis_price_index=current_median_p50)
    return ctx


def macro_rng(seed: int, tick_id: int, episode_id: int = 0) -> np.random.Generator:
    """Детерминированный RNG для macro/churn (Spec 011 §9.5)."""
    sub = int(
        np.random.SeedSequence([seed, tick_id, _MACRO_SALT, episode_id]).generate_state(1)[0]
    )
    return np.random.default_rng(sub)


def _segment_strings(pvd_col: pl.Series) -> np.ndarray:
    if pvd_col.dtype == pl.Categorical:
        return pvd_col.cast(pl.String).to_numpy()
    return pvd_col.to_numpy().astype(str)


def _segment_lookup(segments: np.ndarray, values: dict[str, float]) -> np.ndarray:
    out = np.zeros(segments.shape[0], dtype=np.float64)
    for seg, value in values.items():
        out[segments == seg] = value
    return out


def _segment_alpha_budget(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.alpha_budget_rich,
        "standard": elasticity.alpha_budget_standard,
        "low": elasticity.alpha_budget_low,
    }


def _segment_alpha_freq(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.alpha_freq_rich,
        "standard": elasticity.alpha_freq_standard,
        "low": elasticity.alpha_freq_low,
    }


def _segment_alpha_budget_boom(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.alpha_budget_boom_rich,
        "standard": elasticity.alpha_budget_boom_standard,
        "low": elasticity.alpha_budget_boom_low,
    }


def _segment_alpha_freq_boom(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.alpha_freq_boom_rich,
        "standard": elasticity.alpha_freq_boom_standard,
        "low": elasticity.alpha_freq_boom_low,
    }


def _segment_k_scar(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.k_scar_rich,
        "standard": elasticity.k_scar_standard,
        "low": elasticity.k_scar_low,
    }


def _segment_p_churn(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.p_churn_rich,
        "standard": elasticity.p_churn_standard,
        "low": elasticity.p_churn_low,
    }


def _segment_churn_threshold(elasticity: SegmentElasticityConfig) -> dict[str, float]:
    return {
        "rich": elasticity.churn_stress_threshold_rich,
        "standard": elasticity.churn_stress_threshold_standard,
        "low": elasticity.churn_stress_threshold_low,
    }


def _update_scar_factors(
    scar: np.ndarray,
    segments: np.ndarray,
    macro: MacroState,
    config: MacroDynamicsConfig,
) -> np.ndarray:
    if macro.regime != MacroRegime.STRESS or macro.stress <= config.scar_threshold:
        return scar
    excess = max(0.0, macro.stress - config.scar_threshold)
    if excess <= 0.0:
        return scar
    k_scar = _segment_lookup(segments, _segment_k_scar(config.segment_elasticity))
    return np.clip(scar + k_scar * excess, 0.0, config.scar_cap).astype(np.float32)


def _compute_effective_columns(
    baseline: np.ndarray,
    freq_baseline: np.ndarray,
    scar: np.ndarray,
    segments: np.ndarray,
    macro: MacroState,
    config: MacroDynamicsConfig,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Полный пересчёт mult и effective из baseline + macro (§3.4, §3.9)."""
    bounds = config.buyer_bounds
    elasticity = config.segment_elasticity
    stress = float(macro.stress)
    expansion = float(macro.expansion)

    alpha_budget = _segment_lookup(segments, _segment_alpha_budget(elasticity))
    alpha_freq = _segment_lookup(segments, _segment_alpha_freq(elasticity))
    alpha_budget_boom = _segment_lookup(segments, _segment_alpha_budget_boom(elasticity))
    alpha_freq_boom = _segment_lookup(segments, _segment_alpha_freq_boom(elasticity))

    budget_mult_crash = 1.0 - alpha_budget * (stress ** config.beta_budget)
    freq_mult_crash = 1.0 - alpha_freq * (stress ** config.beta_freq)
    budget_mult_boom = 1.0 + alpha_budget_boom * (expansion ** config.beta_boom)
    freq_mult_boom = 1.0 + alpha_freq_boom * (expansion ** config.beta_boom)

    budget_mult = budget_mult_crash * budget_mult_boom
    freq_mult = np.minimum(freq_mult_crash * freq_mult_boom, config.freq_mult_cap)

    budget_mult = np.clip(
        budget_mult,
        bounds.min_budget_mult,
        bounds.max_budget_mult,
    )

    budget_effective = baseline * (1.0 - scar) * budget_mult
    freq_effective = freq_baseline * freq_mult

    floor = np.maximum(
        baseline.astype(np.float64) * bounds.min_budget_fraction,
        bounds.budget_floor_epsilon,
    )
    ceiling = baseline.astype(np.float64) * bounds.max_budget_mult * (1.0 - scar)
    budget_effective = np.clip(budget_effective, floor, ceiling).astype(np.float32)

    freq_cap = np.minimum(1.0, freq_baseline.astype(np.float64) * config.freq_mult_cap)
    freq_effective = np.clip(freq_effective, 0.0, freq_cap).astype(np.float32)
    freq_floor = freq_baseline.astype(np.float64) * bounds.min_freq_fraction
    freq_effective = np.maximum(freq_effective, freq_floor).astype(np.float32)

    return budget_mult, freq_mult, budget_effective, freq_effective


def apply_buyer_economic_state(
    buyers_df: pl.DataFrame,
    macro: MacroState,
    config: MacroDynamicsConfig,
    rng: np.random.Generator,
) -> pl.DataFrame:
    """
    Пересчитывает scar/churn и effective-колонки из baseline + macro.
    Legacy budget / purchase_frequency не мутируются.
    """
    if buyers_df.height == 0:
        return buyers_df.clone()

    df = ensure_buyer_economic_columns(buyers_df).clone()
    segments = _segment_strings(df[COL_PVD_SEGMENT])

    baseline = df[COL_BUDGET_BASELINE].to_numpy().astype(np.float64)
    freq_baseline = df[COL_FREQ_BASELINE].to_numpy().astype(np.float64)
    scar = df[COL_SCAR_FACTOR].to_numpy().astype(np.float64)
    is_churned = df[COL_IS_CHURNED].to_numpy()

    scar = _update_scar_factors(scar, segments, macro, config).astype(np.float64)
    budget_mult, freq_mult, budget_effective, freq_effective = _compute_effective_columns(
        baseline,
        freq_baseline,
        scar,
        segments,
        macro,
        config,
    )

    if macro.stress > 0.0:
        p_churn = _segment_lookup(segments, _segment_p_churn(config.segment_elasticity))
        churn_threshold = _segment_lookup(
            segments,
            _segment_churn_threshold(config.segment_elasticity),
        )
        churn_draw = rng.random(is_churned.shape[0])
        new_churn = (
            (~is_churned)
            & (macro.stress > churn_threshold)
            & (churn_draw < p_churn * macro.stress)
        )
        is_churned = is_churned | new_churn

    freq_effective = np.where(is_churned, 0.0, freq_effective).astype(np.float32)

    return df.with_columns(
        pl.Series(COL_SCAR_FACTOR, scar.astype(np.float32)),
        pl.Series(COL_BUDGET_EFFECTIVE, budget_effective),
        pl.Series(COL_FREQ_EFFECTIVE, freq_effective),
        pl.Series(COL_IS_CHURNED, is_churned),
    )


def crisis_scenario_config(name: str | None) -> CrisisScenarioConfig:
    """Разрешает preset сценария кризиса (Spec 011 §8.2)."""
    if name == "mild":
        return CrisisScenarioConfig.mild()
    if name == "severe":
        return CrisisScenarioConfig.severe()
    return CrisisScenarioConfig.standard()


def estimate_stress_half_life_ticks(stress: float, config: MacroDynamicsConfig) -> float:
    """Оценка ticks до stress/2 для cyber-log narrative (Spec 011 §10.3)."""
    if stress <= 0.0:
        return 0.0
    target = stress / 2.0
    current = stress
    ticks = 0
    while current > target and ticks < 500:
        if config.decay_mode == "nonlinear_drain":
            current = max(
                current - config.decay_rate * (current ** config.decay_exponent),
                0.0,
            )
        else:
            current *= config.persistence_stress
        ticks += 1
    return float(ticks)


def resolve_demand_shocks_to_macro(
    ctx: SimulationContext,
    config: MacroDynamicsConfig,
    rng: np.random.Generator,
) -> SimulationContext:
    """Stochastic mode: demand ActiveShock → macro impulse, без timed overlay."""
    if config.shock_mode == "fixed_duration":
        return ctx

    ctx_next = ctx
    kept: list = []
    impulse_logs: list[DemandImpulseLog] = list(ctx.pending_demand_impulse_logs)
    for shock in ctx.active_shocks:
        if shock.shock_type in (ShockType.DEMAND_CRASH, ShockType.DEMAND_BOOM):
            scenario_name = shock.scenario or "standard"
            scenario_cfg = crisis_scenario_config(scenario_name)
            cmd = ShockCommand(
                shock_type=shock.shock_type,
                intensity=shock.intensity,
                duration_ticks=shock.remaining_ticks,
                scenario=scenario_name,
            )
            stress_before = ctx_next.macro.stress
            expansion_before = ctx_next.macro.expansion
            ctx_next = apply_demand_impulse(
                ctx_next, cmd, config, rng, scenario=scenario_cfg
            )
            if shock.shock_type == ShockType.DEMAND_BOOM:
                impulse = max(ctx_next.macro.expansion - expansion_before, 0.0)
                half_life = estimate_stress_half_life_ticks(
                    ctx_next.macro.expansion,
                    config,
                )
            else:
                impulse = max(ctx_next.macro.stress - stress_before, 0.0)
                half_life = estimate_stress_half_life_ticks(
                    ctx_next.macro.stress,
                    config,
                )
            impulse_logs.append(
                DemandImpulseLog(
                    shock_type=shock.shock_type.value,
                    scenario=scenario_name,
                    impulse=float(impulse),
                    stress_after=ctx_next.macro.stress,
                    est_half_life_ticks=half_life,
                )
            )
        else:
            kept.append(shock)
    return replace(
        ctx_next,
        active_shocks=tuple(kept),
        pending_demand_impulse_logs=tuple(impulse_logs),
    )


def run_macro_tick(
    ctx: SimulationContext,
    buyers_df: pl.DataFrame,
    config: MacroDynamicsConfig,
    rng: np.random.Generator,
    *,
    current_median_p50: float | None = None,
) -> tuple[SimulationContext, pl.DataFrame]:
    """Полный macro-тик: resolve impulses → feedback → advance → buyer economic state."""
    if config.shock_mode == "fixed_duration":
        return ctx, ensure_buyer_economic_columns(buyers_df)

    previous_regime = ctx.macro.regime
    ctx = resolve_demand_shocks_to_macro(ctx, config, rng)
    if current_median_p50 is not None:
        ctx = update_pre_crisis_price_index(
            ctx,
            previous_regime=previous_regime,
            current_median_p50=current_median_p50,
        )
        ctx = apply_market_price_feedback(ctx, config, current_median_p50)
    ctx = advance_macro_state(ctx, config, rng)
    buyers_out = apply_buyer_economic_state(buyers_df, ctx.macro, config, rng)
    return ctx, buyers_out

