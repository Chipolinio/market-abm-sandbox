# Spec 014 §13.1 — in-memory macro snapshot + ETA (slice 14.1).
from __future__ import annotations

from market_abm.analytics.macro_snapshot import (
    MacroSnapshotMemory,
    build_active_shock_dtos,
    build_macro_state_dto,
    estimate_recovery_eta,
    write_macro_snapshot,
)
from market_abm.config.macro import MacroDynamicsConfig
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.simulation.context import SimulationContext, tick_down_active_shocks


def test_14_1_t1_macro_snapshot_roundtrip() -> None:
    memory = MacroSnapshotMemory()
    macro = MacroState(
        stress=0.72,
        expansion=0.0,
        regime=MacroRegime.STRESS,
        peak_stress=0.72,
        peak_expansion=0.0,
        episode_id=3,
        ticks_in_episode=5,
    )
    shocks = (
        ActiveShock(
            shock_type=ShockType.DEMAND_CRASH,
            intensity=1.0,
            remaining_ticks=12,
            applied_at_tick=10,
            scenario="severe",
        ),
    )
    cfg = MacroDynamicsConfig(stress_cap=1.2, expansion_cap=0.8)

    write_macro_snapshot(
        memory,
        tick_id=10,
        macro=macro,
        active_shocks=shocks,
        ref_price=None,
        config=cfg,
    )
    snap = memory.read(tick_id=10)
    assert snap is not None
    assert snap.tick_id == 10
    assert snap.macro_state["stress"] == 0.72
    assert snap.macro_state["regime"] == "stress"
    assert snap.macro_state["episode_id"] == 3
    assert snap.macro_state["stress_cap"] == 1.2
    assert snap.macro_state["expansion_cap"] == 0.8
    assert len(snap.active_shocks) == 1
    assert snap.active_shocks[0]["shock_type"] == "demand_crash"
    assert snap.active_shocks[0]["remaining_ticks"] == 12

    latest = memory.read(None)
    assert latest is not None
    assert latest.tick_id == 10


def test_14_1_t4_estimate_recovery_eta_none_in_normal() -> None:
    cfg = MacroDynamicsConfig()
    normal = MacroState(regime=MacroRegime.NORMAL, stress=0.0, expansion=0.0)
    assert estimate_recovery_eta(normal, cfg) is None

    expansion = MacroState(regime=MacroRegime.EXPANSION, stress=0.0, expansion=0.4)
    assert estimate_recovery_eta(expansion, cfg) is None

    stress = MacroState(
        regime=MacroRegime.STRESS,
        stress=0.55,
        expansion=0.0,
        peak_stress=0.55,
        episode_id=1,
    )
    eta = estimate_recovery_eta(stress, cfg)
    assert eta is not None
    assert eta > 0
    assert eta <= 500


def test_14_1_t5_expired_shock_absent_from_snapshot() -> None:
    ctx = SimulationContext(
        tick_id=0,
        active_shocks=(
            ActiveShock(
                shock_type=ShockType.PLATFORM_FEE_HIKE,
                intensity=1.0,
                remaining_ticks=1,
                applied_at_tick=0,
                scenario=None,
            ),
        ),
        platform_fee_rate=0.15,
    )
    ctx_next = tick_down_active_shocks(ctx, macro_config=MacroDynamicsConfig(shock_mode="fixed_duration"))
    assert ctx_next.active_shocks == ()

    dtos = build_active_shock_dtos(ctx_next.active_shocks)
    assert dtos == []

    memory = MacroSnapshotMemory()
    write_macro_snapshot(
        memory,
        tick_id=1,
        macro=MacroState.empty(),
        active_shocks=ctx_next.active_shocks,
        ref_price=None,
        config=MacroDynamicsConfig(),
    )
    snap = memory.read(1)
    assert snap is not None
    assert snap.active_shocks == []


def test_build_macro_state_dto_includes_caps_and_eta() -> None:
    macro = MacroState(regime=MacroRegime.RECOVERY, stress=0.08, expansion=0.0, episode_id=2)
    cfg = MacroDynamicsConfig(stress_cap=1.5, expansion_cap=0.9)
    dto = build_macro_state_dto(
        macro,
        stress_cap=cfg.stress_cap,
        expansion_cap=cfg.expansion_cap,
        est_recovery_eta_ticks=7,
    )
    assert dto["stress_cap"] == 1.5
    assert dto["expansion_cap"] == 0.9
    assert dto["est_recovery_eta_ticks"] == 7
    assert dto["regime"] == "recovery"
