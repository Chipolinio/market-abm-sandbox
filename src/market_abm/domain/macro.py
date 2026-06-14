# Назначение файла: доменные типы макро-состояния (Slice 11.1, Spec 011 §3.1).
# Базовая идея: скаляры stress/expansion + regime enum, без polars/scipy runtime.
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MacroRegime(str, Enum):
    """Фаза макро-эпизода спроса."""

    NORMAL = "normal"
    STRESS = "stress"
    EXPANSION = "expansion"
    RECOVERY = "recovery"


@dataclass
class MacroState:
    """Runtime macro state в SimulationContext (не Pydantic)."""

    stress: float = 0.0
    expansion: float = 0.0
    regime: MacroRegime = MacroRegime.NORMAL
    peak_stress: float = 0.0
    peak_expansion: float = 0.0
    episode_id: int = 0
    ticks_in_episode: int = 0

    @classmethod
    def empty(cls) -> MacroState:
        """Начальное состояние до первого импульса."""
        return cls()


@dataclass(frozen=True)
class DemandImpulseLog:
    """Снимок импульса demand shock для cyber-log (Spec 011 §10.3)."""

    shock_type: str
    scenario: str
    impulse: float
    stress_after: float
    est_half_life_ticks: float
