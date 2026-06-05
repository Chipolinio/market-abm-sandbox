# Назначение файла: drain shock_queue → SimulationContext (Slice 8.1).
# Базовая идея: queue.Queue для детерминизма в pytest; production — mp.Queue (см. SimulationWorker).
from __future__ import annotations

import queue

from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import (
    ShockCommand,
    SimulationContext,
    drain_shock_queue,
)


def test_shock_queue_drain_merges_context() -> None:
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    shock_queue.put_nowait(
        ShockCommand(ShockType.DEMAND_CRASH, intensity=1.0, duration_ticks=10)
    )
    shock_queue.put_nowait(
        ShockCommand(ShockType.PLATFORM_FEE_HIKE, intensity=1.0, duration_ticks=15)
    )

    ctx = SimulationContext(tick_id=3, active_shocks=(), platform_fee_rate=0.15)
    ctx_next = drain_shock_queue(shock_queue, ctx)

    assert len(ctx_next.active_shocks) == 2
    assert shock_queue.empty()
