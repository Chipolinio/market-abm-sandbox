# Назначение файла: доменные типы шоков среды (Slice 8.1).
# Базовая идея: enum + frozen dataclass без polars/scipy runtime.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ShockType(str, Enum):
    """Типы макро-шоков, применяемых к buyers_df / products_df."""

    DEMAND_CRASH = "demand_crash"
    DEMAND_BOOM = "demand_boom"
    PLATFORM_FEE_HIKE = "platform_fee_hike"
    PLATFORM_FEE_CUT = "platform_fee_cut"
    MARKETPLACE_PROMOTION = "marketplace_promotion"
    SUPPLY_SHOCK = "supply_shock"


@dataclass(frozen=True)
class ActiveShock:
    """Активный шок в SimulationContext."""

    shock_type: ShockType
    intensity: float
    remaining_ticks: int
    applied_at_tick: int
    scenario: str | None = None
