# Назначение файла: severe recession integration — 120 ticks (Slice 11.6, Spec 011 §13.6).
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import polars as pl
import pytest

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.macro import CrisisScenarioConfig, MacroDynamicsConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_PRICE_PAID,
    COL_PVD_SEGMENT,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
)
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.context import tick_down_active_shocks, with_tick_id
from market_abm.simulation.extended_runtime import ExtendedSimulationState, init_extended_state
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.macro import macro_rng, median_listing_price, run_macro_tick
from market_abm.simulation.runner import _bootstrap_products_from_listings, _bootstrap_rng, _maybe_rechunk_products
from market_abm.simulation.step import step

N_TICKS: int = 120
SHOCK_TICK: int = 35
BASELINE_START: int = 10
BASELINE_END: int = 30
POST_RECOVERY_START: int = 100
POST_RECOVERY_END: int = 120

pytestmark = pytest.mark.slow


@dataclass(frozen=True)
class RecessionRunResult:
    seed: int
    stress_path: tuple[float, ...]
    gmv_by_tick: tuple[float, ...]
    transactions_by_tick: tuple[pl.DataFrame, ...]
    buyers_df: pl.DataFrame
    sellers_df: pl.DataFrame
    shock_tick: int
    peak_stress: float
    peak_tick: int


def _severe_macro_config() -> MacroDynamicsConfig:
    severe = CrisisScenarioConfig.severe()
    return MacroDynamicsConfig(
        shock_mode="stochastic_regime",
        impulse_mean=severe.impulse_mean,
        impulse_sigma=severe.impulse_sigma,
        decay_rate=severe.decay_rate,
        decay_mode="nonlinear_drain",
        scar_cap=severe.scar_cap,
        feedback_gain=0.15,
    )


def _recession_run_config(*, seed: int, n_buyers: int = 250, n_sellers: int = 24) -> SimulationRunConfig:
    buyers_batch_size = min(max(n_buyers, 101), 300)
    repricing = RepricingConfig.market_with_headroom()
    return SimulationRunConfig(
        seed=seed,
        runtime_mode="extended",
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=50,
            buyers_batch_size=buyers_batch_size,
            outside_utility_bias=-100.0,
            outside_utility_bias_by_pvd_segment=ChoiceModelConfig.default_segment_biases(),
            income_utility_gamma=0.35,
        ),
        repricing=repricing,
        macro_dynamics=_severe_macro_config(),
    )


def _crash_shock(tick_id: int) -> ActiveShock:
    return ActiveShock(
        shock_type=ShockType.DEMAND_CRASH,
        intensity=1.0,
        remaining_ticks=0,
        applied_at_tick=tick_id,
    )


def run_severe_recession(
    *,
    seed: int,
    n_ticks: int = N_TICKS,
    shock_tick: int = SHOCK_TICK,
    n_buyers: int = 250,
    n_sellers: int = 24,
) -> RecessionRunResult:
    """Extended simulation with severe crash impulse at shock_tick."""
    config = _recession_run_config(seed=seed, n_buyers=n_buyers, n_sellers=n_sellers)
    buyers_df = generate_buyers(
        BuyerPopulationConfig.default_market(n_buyers=n_buyers, seed=seed)
    )
    sellers_df = generate_sellers(
        SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
    )
    listings_df = initialize_listings(
        sellers_df,
        ListingInitConfig.market_with_headroom(),
        seed=seed,
        min_listing_price=config.repricing.min_listing_price,
    )

    rng = _bootstrap_rng(config.seed)
    products_df = _bootstrap_products_from_listings(
        listings_df,
        config=config.products_bootstrap,
        rng=rng,
        sellers_df=sellers_df,
    )
    extended_state = init_extended_state(sellers_df)
    buyers_runtime = buyers_df

    stress_path: list[float] = []
    gmv_by_tick: list[float] = []
    transactions_by_tick: list[pl.DataFrame] = []

    for tick_id in range(n_ticks):
        sim_ctx = with_tick_id(extended_state.simulation_context, tick_id)
        if tick_id == shock_tick:
            sim_ctx = replace(
                sim_ctx,
                active_shocks=sim_ctx.active_shocks + (_crash_shock(tick_id),),
            )

        tick_rng = macro_rng(
            config.seed or 0,
            tick_id,
            sim_ctx.macro.episode_id,
        )
        sim_ctx, buyers_runtime = run_macro_tick(
            sim_ctx,
            buyers_runtime,
            config.macro_dynamics,
            tick_rng,
            current_median_p50=median_listing_price(products_df),
        )

        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=config.seed,
            choice=config.choice,
            repricing=config.repricing,
            economics=config.economics,
        )
        products_next, transactions_df, sellers_state_next = step(
            buyers_runtime,
            sellers_df,
            products_df,
            step_config,
            sellers_state_df=extended_state.sellers_state_df,
            simulation_context=sim_ctx,
            shock_catalog=config.shock_catalog,
            macro_config=config.macro_dynamics,
        )
        if sellers_state_next is None:
            raise RuntimeError("extended recession run requires sellers_state_next")

        products_df = _maybe_rechunk_products(products_next)
        stress_path.append(sim_ctx.macro.stress)
        gmv_by_tick.append(
            float(transactions_df[COL_PRICE_PAID].sum()) if transactions_df.height > 0 else 0.0
        )
        transactions_by_tick.append(transactions_df)

        extended_state = replace(
            extended_state,
            sellers_state_df=sellers_state_next,
            simulation_context=with_tick_id(sim_ctx, tick_id + 1),
        )
        extended_state = replace(
            extended_state,
            simulation_context=tick_down_active_shocks(
                extended_state.simulation_context,
                macro_config=config.macro_dynamics,
            ),
        )

    post_shock = stress_path[shock_tick:]
    peak_stress = max(post_shock)
    peak_tick = shock_tick + post_shock.index(peak_stress)

    return RecessionRunResult(
        seed=seed,
        stress_path=tuple(stress_path),
        gmv_by_tick=tuple(gmv_by_tick),
        transactions_by_tick=tuple(transactions_by_tick),
        buyers_df=buyers_df,
        sellers_df=sellers_df,
        shock_tick=shock_tick,
        peak_stress=peak_stress,
        peak_tick=peak_tick,
    )


def _mean(values: tuple[float, ...]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _window(values: tuple[float, ...], start: int, end: int) -> tuple[float, ...]:
    return values[start:end]


def _asymmetric_timing(result: RecessionRunResult) -> tuple[int, int]:
    stress = result.stress_path
    shock_tick = result.shock_tick
    peak_tick = result.peak_tick
    half = result.peak_stress / 2.0

    rise_half_tick = next(
        (t for t in range(shock_tick, peak_tick + 1) if stress[t] >= half),
        shock_tick,
    )
    recovery_half_tick = next(
        (t for t in range(peak_tick, len(stress)) if stress[t] <= half),
        len(stress) - 1,
    )
    time_to_half_drop = rise_half_tick - shock_tick
    time_to_half_recovery = recovery_half_tick - peak_tick
    return time_to_half_drop, time_to_half_recovery


def _low_maxvolume_share(
    transactions: pl.DataFrame,
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
) -> float:
    if transactions.height == 0:
        return 0.0
    joined = (
        transactions.join(
            buyers_df.select([COL_BUYER_ID, COL_PVD_SEGMENT]),
            on=COL_BUYER_ID,
            how="left",
        )
        .join(
            sellers_df.select([COL_SELLER_ID, COL_STRATEGY_TYPE]),
            on=COL_SELLER_ID,
            how="left",
        )
        .with_columns(
            pl.col(COL_PVD_SEGMENT).cast(pl.String),
            pl.col(COL_STRATEGY_TYPE).cast(pl.String),
        )
    )
    low_mv = joined.filter(
        (pl.col(COL_PVD_SEGMENT) == "low") & (pl.col(COL_STRATEGY_TYPE) == "MaxVolume")
    )
    return low_mv.height / transactions.height


def _avg_low_maxvolume_share(
    result: RecessionRunResult,
    tick_start: int,
    tick_end: int,
) -> float:
    shares: list[float] = []
    for tick_id in range(tick_start, tick_end):
        shares.append(
            _low_maxvolume_share(
                result.transactions_by_tick[tick_id],
                result.buyers_df,
                result.sellers_df,
            )
        )
    return _mean(tuple(shares))


@pytest.fixture(scope="module")
def severe_recession_run() -> RecessionRunResult:
    return run_severe_recession(seed=42)


def test_11_6_t1_recession_asymmetric_recovery(severe_recession_run: RecessionRunResult) -> None:
    drop_ticks, recovery_ticks = _asymmetric_timing(severe_recession_run)
    assert severe_recession_run.peak_stress > 0.2
    assert recovery_ticks > drop_ticks


def test_11_6_t2_post_recovery_gmv_below_pre_crisis(severe_recession_run: RecessionRunResult) -> None:
    pre = _mean(_window(severe_recession_run.gmv_by_tick, BASELINE_START, BASELINE_END))
    post = _mean(
        _window(severe_recession_run.gmv_by_tick, POST_RECOVERY_START, POST_RECOVERY_END)
    )
    assert pre > 0.0
    assert post < pre


def _peak_crisis_low_maxvolume_share(result: RecessionRunResult) -> float:
    """Max cell share during high-stress window after shock (Spec 011 §4.3 direction)."""
    end = min(result.shock_tick + 30, len(result.stress_path))
    shares: list[float] = []
    for tick_id in range(result.shock_tick, end):
        if result.stress_path[tick_id] < 0.3:
            continue
        tx = result.transactions_by_tick[tick_id]
        if tx.height == 0:
            continue
        shares.append(_low_maxvolume_share(tx, result.buyers_df, result.sellers_df))
    if not shares:
        return 0.0
    return max(shares)


def test_11_6_t3_demand_matrix_low_maxvolume_share_up(severe_recession_run: RecessionRunResult) -> None:
    baseline_share = _avg_low_maxvolume_share(
        severe_recession_run, BASELINE_START, BASELINE_END - 1
    )
    crisis_peak_share = _peak_crisis_low_maxvolume_share(severe_recession_run)
    assert baseline_share > 0.0
    assert crisis_peak_share > baseline_share


def test_11_6_t4_deterministic_recession_with_seed() -> None:
    run_a = run_severe_recession(seed=77)
    run_b = run_severe_recession(seed=77)
    assert run_a.stress_path == run_b.stress_path
    assert run_a.gmv_by_tick == run_b.gmv_by_tick
