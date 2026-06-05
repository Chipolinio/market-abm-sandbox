# Назначение файла: unit-тесты SimulationContext и merge_shock (Slice 8.1).
from __future__ import annotations

from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand, SimulationContext, merge_shock


def test_merge_shock_appends_active_shock() -> None:
    ctx = SimulationContext(tick_id=5, active_shocks=(), platform_fee_rate=0.15)
    cmd = ShockCommand(
        shock_type=ShockType.DEMAND_CRASH,
        intensity=1.0,
        duration_ticks=10,
    )

    ctx_next = merge_shock(ctx, cmd)

    assert len(ctx_next.active_shocks) == 1
    shock = ctx_next.active_shocks[0]
    assert shock.shock_type == ShockType.DEMAND_CRASH
    assert shock.remaining_ticks == 10
    assert shock.applied_at_tick == 5
    assert len(ctx.active_shocks) == 0


def test_merge_two_shocks_produces_two_active() -> None:
    ctx = SimulationContext(tick_id=0, active_shocks=(), platform_fee_rate=0.15)
    cmd_a = ShockCommand(ShockType.DEMAND_CRASH, 1.0, 10)
    cmd_b = ShockCommand(ShockType.PLATFORM_FEE_HIKE, 1.0, 15)

    ctx_one = merge_shock(ctx, cmd_a)
    ctx_two = merge_shock(ctx_one, cmd_b)

    assert len(ctx_two.active_shocks) == 2
    types = {s.shock_type for s in ctx_two.active_shocks}
    assert types == {ShockType.DEMAND_CRASH, ShockType.PLATFORM_FEE_HIKE}
