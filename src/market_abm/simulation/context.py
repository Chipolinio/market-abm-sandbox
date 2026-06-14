# Назначение файла: SimulationContext и IPC-команды шоков (Slice 8.1).
# Базовая идея: dataclass-контекст тика; merge/drain — чистые функции.
from __future__ import annotations

import queue
import time
from dataclasses import dataclass, field, replace

from market_abm.domain.constants import PLATFORM_DEFAULTS, COL_BASE_COMMISSION
from market_abm.config.macro import MacroDynamicsConfig
from market_abm.config.shocks import ShockCatalogConfig
from market_abm.domain.macro import MacroState
from market_abm.domain.shocks import ActiveShock, ShockType


@dataclass(frozen=True)
class ShockCommand:
    """Pickle-safe DTO для shock_queue (enum + scalars)."""

    shock_type: ShockType
    intensity: float
    duration_ticks: int


@dataclass
class SimulationContext:
    """Снимок контекста симуляции на тик (не Pydantic)."""

    tick_id: int
    active_shocks: tuple[ActiveShock, ...]
    platform_fee_rate: float
    macro: MacroState = field(default_factory=MacroState.empty)


def default_simulation_context(*, tick_id: int = 0) -> SimulationContext:
    """Контекст с дефолтной комиссией платформы."""
    return SimulationContext(
        tick_id=tick_id,
        active_shocks=(),
        platform_fee_rate=PLATFORM_DEFAULTS[COL_BASE_COMMISSION],
    )


def merge_shock(ctx: SimulationContext, cmd: ShockCommand) -> SimulationContext:
    """Добавляет ActiveShock; исходный ctx не мутируется."""
    shock = ActiveShock(
        shock_type=cmd.shock_type,
        intensity=cmd.intensity,
        remaining_ticks=cmd.duration_ticks,
        applied_at_tick=ctx.tick_id,
    )
    return replace(ctx, active_shocks=ctx.active_shocks + (shock,))


_DRAIN_IDLE_SEC: float = 0.05


def drain_shock_queue(shock_queue: queue.Queue, ctx: SimulationContext) -> SimulationContext:
    """
    Сливает все команды из очереди в active_shocks.
    macOS: mp.Queue.get_nowait() может вернуть Empty при непустой очереди (feeder thread);
    после первого успешного get ждём короткий idle-timeout перед выходом.
    """
    ctx_next = ctx
    got_any = False
    idle_deadline: float | None = None

    while True:
        try:
            cmd = shock_queue.get_nowait()
        except queue.Empty:
            if not got_any:
                break
            now = time.monotonic()
            if idle_deadline is None:
                idle_deadline = now + _DRAIN_IDLE_SEC
            elif now >= idle_deadline:
                break
            time.sleep(0.005)
            continue

        ctx_next = merge_shock(ctx_next, cmd)
        got_any = True
        idle_deadline = None

    return ctx_next


def with_tick_id(ctx: SimulationContext, tick_id: int) -> SimulationContext:
    """Обновляет tick_id контекста без мутации исходного объекта."""
    return replace(ctx, tick_id=tick_id)


def tick_down_active_shocks(
    ctx: SimulationContext,
    *,
    macro_config: MacroDynamicsConfig | None = None,
) -> SimulationContext:
    """Уменьшает remaining_ticks; demand shocks в stochastic mode не таймерятся."""
    demand_timed = (
        macro_config is None or macro_config.shock_mode == "fixed_duration"
    )
    remaining: list[ActiveShock] = []
    for shock in ctx.active_shocks:
        if shock.shock_type in (ShockType.DEMAND_CRASH, ShockType.DEMAND_BOOM) and not demand_timed:
            continue
        if shock.remaining_ticks <= 1:
            continue
        remaining.append(replace(shock, remaining_ticks=shock.remaining_ticks - 1))
    return replace(ctx, active_shocks=tuple(remaining))


def active_demand_shock_types(ctx: SimulationContext) -> list[ShockType]:
    """Типы demand-шоков, активные на текущем тике (для command-side system_events)."""
    return [
        shock.shock_type
        for shock in ctx.active_shocks
        if shock.shock_type in (ShockType.DEMAND_CRASH, ShockType.DEMAND_BOOM)
    ]


def demand_shock_pct_drop(
    shock_type: ShockType,
    *,
    catalog: ShockCatalogConfig,
    intensity: float,
) -> float:
    """Процент изменения бюджета для cyber-log message."""
    if shock_type == ShockType.DEMAND_CRASH:
        mult = catalog.demand_crash.budget_multiplier * intensity
        return max(0.0, (1.0 - mult) * 100.0)
    mult = catalog.demand_boom.budget_multiplier * intensity
    return max(0.0, (mult - 1.0) * 100.0)


def demand_shock_pct_frequency_change(
    shock_type: ShockType,
    *,
    catalog: ShockCatalogConfig,
    intensity: float,
) -> float:
    """Процент изменения purchase_frequency (канал A, Spec 010 §7.1)."""
    spec = (
        catalog.demand_crash
        if shock_type == ShockType.DEMAND_CRASH
        else catalog.demand_boom
    )
    if not spec.scale_purchase_frequency:
        return 0.0
    mult = spec.purchase_frequency_multiplier * intensity
    if shock_type == ShockType.DEMAND_CRASH:
        return max(0.0, (1.0 - mult) * 100.0)
    return max(0.0, (mult - 1.0) * 100.0)
