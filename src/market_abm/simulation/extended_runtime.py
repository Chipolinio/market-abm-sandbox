# Назначение файла: extended runtime state и post-tick pipeline (Slice 8.4).
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import polars as pl

from market_abm.analytics.events import (
    append_system_events,
    build_demand_shock_event,
    build_tick_pulse_event,
    coalesce_bankruptcy_events,
    detect_system_events,
)
from market_abm.analytics.persist import (
    persist_sellers_state_snapshot,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.runner import SimulationRunConfig
from market_abm.domain.constants import (
    COL_IS_BANKRUPT,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_WORKING_CAPITAL,
)
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import (
    SimulationContext,
    default_simulation_context,
    demand_shock_pct_drop,
    demand_shock_pct_frequency_change,
    tick_down_active_shocks,
    with_tick_id,
)
from market_abm.simulation.seller_economics import init_sellers_state, new_bankruptcy_seller_ids


@dataclass
class ExtendedSimulationState:
    """Mutable runtime snapshot для extended mode (воркер / runner)."""

    sellers_state_df: pl.DataFrame
    simulation_context: SimulationContext
    cumulative_gmv: float = 0.0
    event_seq: int = 0


def init_extended_state(
    sellers_df: pl.DataFrame,
    *,
    tick_id: int = 0,
) -> ExtendedSimulationState:
    return ExtendedSimulationState(
        sellers_state_df=init_sellers_state(sellers_df),
        simulation_context=default_simulation_context(tick_id=tick_id),
    )


def _top_seller_ids(sellers_state: pl.DataFrame, *, n: int = 3) -> frozenset[int]:
    """Топ-N по working_capital до банкротств на тике (для VIP-событий)."""
    if sellers_state.height == 0:
        return frozenset()
    active = sellers_state.filter(~pl.col(COL_IS_BANKRUPT))
    if active.height == 0:
        return frozenset()
    top = (
        active.sort(COL_WORKING_CAPITAL, descending=True)
        .head(n)[COL_SELLER_ID]
        .to_list()
    )
    return frozenset(int(sid) for sid in top)


def _build_command_side_events(
    *,
    run_id: str,
    tick_id: int,
    simulation_context: SimulationContext,
    prev_sellers_state: pl.DataFrame,
    next_sellers_state: pl.DataFrame,
    config: SimulationRunConfig,
    seq_start: int,
) -> tuple[list[dict[str, object]], int]:
    events: list[dict[str, object]] = []
    seq = seq_start

    seen_demand: set[ShockType] = set()
    for shock in simulation_context.active_shocks:
        if shock.shock_type not in (ShockType.DEMAND_CRASH, ShockType.DEMAND_BOOM):
            continue
        if shock.shock_type in seen_demand:
            continue
        seen_demand.add(shock.shock_type)
        spec = (
            config.shock_catalog.demand_crash
            if shock.shock_type == ShockType.DEMAND_CRASH
            else config.shock_catalog.demand_boom
        )
        intensity = shock.intensity
        pct_budget = demand_shock_pct_drop(
            shock.shock_type,
            catalog=config.shock_catalog,
            intensity=intensity,
        )
        pct_freq = demand_shock_pct_frequency_change(
            shock.shock_type,
            catalog=config.shock_catalog,
            intensity=intensity,
        )
        budget_mult = spec.budget_multiplier * intensity
        freq_mult = (
            spec.purchase_frequency_multiplier * intensity
            if spec.scale_purchase_frequency
            else None
        )
        events.append(
            build_demand_shock_event(
                run_id=run_id,
                tick_id=tick_id,
                seq=seq,
                pct_drop=pct_budget,
                shock_type=shock.shock_type,
                pct_frequency_change=pct_freq if freq_mult is not None else None,
                budget_multiplier=budget_mult,
                purchase_frequency_multiplier=freq_mult,
            )
        )
        seq += 1

    bankrupt_ids = [int(s) for s in new_bankruptcy_seller_ids(prev_sellers_state, next_sellers_state)]
    top_ids = _top_seller_ids(prev_sellers_state)
    bankruptcy_events, seq = coalesce_bankruptcy_events(
        run_id=run_id,
        tick_id=tick_id,
        bankrupt_seller_ids=bankrupt_ids,
        top_seller_ids=top_ids,
        seq_start=seq,
    )
    events.extend(bankruptcy_events)

    return events, seq


def persist_extended_tick(
    run_root: Path,
    *,
    tick_id: int,
    transactions_df: pl.DataFrame,
    products_df: pl.DataFrame,
    state: ExtendedSimulationState,
    prev_sellers_state: pl.DataFrame,
    config: SimulationRunConfig,
    con: duckdb.DuckDBPyConnection,
    run_id: str,
) -> ExtendedSimulationState:
    """Persist tick artifacts + command-side / detector system_events."""
    persist_tick_artifacts(
        run_root,
        tick_id=tick_id,
        transactions_df=transactions_df,
        products_df=products_df,
        config=config.persistence,
        con=con,
    )
    persist_sellers_state_snapshot(
        run_root,
        tick_id=tick_id,
        sellers_state_df=state.sellers_state_df,
        con=con,
    )

    cmd_events, seq = _build_command_side_events(
        run_id=run_id,
        tick_id=tick_id,
        simulation_context=state.simulation_context,
        prev_sellers_state=prev_sellers_state,
        next_sellers_state=state.sellers_state_df,
        config=config,
        seq_start=state.event_seq,
    )

    tick_gmv = float(transactions_df[COL_PRICE_PAID].sum()) if transactions_df.height > 0 else 0.0
    tx_count = transactions_df.height
    bankrupt_count = int(state.sellers_state_df.filter(pl.col(COL_IS_BANKRUPT)).height)
    active_count = int(state.sellers_state_df.height) - bankrupt_count
    cmd_events.append(
        build_tick_pulse_event(
            run_id=run_id,
            tick_id=tick_id,
            seq=seq,
            gmv=tick_gmv,
            transaction_count=tx_count,
            active_sellers=active_count,
            bankrupt_sellers=bankrupt_count,
        )
    )
    seq += 1

    if cmd_events:
        append_system_events(run_root, pl.DataFrame(cmd_events), con)

    if tick_id % config.events.check_every_n_ticks == 0:
        store = AnalyticsStore(run_root)
        try:
            detected = detect_system_events(
                store,
                as_of_tick=tick_id,
                config=config.events,
                run_id=run_id,
            )
        finally:
            store.close()
        if detected.height > 0:
            append_system_events(run_root, detected, con)

    return ExtendedSimulationState(
        sellers_state_df=state.sellers_state_df,
        simulation_context=tick_down_active_shocks(
            with_tick_id(state.simulation_context, tick_id + 1)
        ),
        cumulative_gmv=state.cumulative_gmv + tick_gmv,
        event_seq=seq,
    )
