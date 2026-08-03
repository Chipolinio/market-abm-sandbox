# Spec 014 §4.5 — in-memory macro / active_shocks snapshot for WS (no per-tick disk I/O).
from __future__ import annotations

import json
from dataclasses import dataclass, field

from market_abm.config.macro import MacroDynamicsConfig
from market_abm.domain.macro import MacroState
from market_abm.domain.shocks import ActiveShock
from market_abm.simulation.macro import estimate_recovery_eta

# Re-export for callers / tests that import ETA from analytics layer.
__all__ = [
    "MacroSnapshotMemory",
    "MacroTickSnapshot",
    "build_active_shock_dtos",
    "build_macro_state_dto",
    "clear_macro_snapshot_ipc",
    "estimate_recovery_eta",
    "read_macro_snapshot_ipc",
    "snapshot_from_json_bytes",
    "snapshot_to_json_bytes",
    "write_macro_snapshot",
    "write_macro_snapshot_ipc",
]


@dataclass(frozen=True)
class MacroTickSnapshot:
    """One tick of macro observability state (in-memory only)."""

    tick_id: int
    macro_state: dict[str, object]
    active_shocks: list[dict[str, object]]
    ref_price: float | None = None


@dataclass
class MacroSnapshotMemory:
    """
    In-memory ring of macro snapshots (Spec 014 §2.2).
    No disk I/O — API/broadcaster reads via attach on AnalyticsStore or IPC slot.
    """

    _by_tick: dict[int, MacroTickSnapshot] = field(default_factory=dict)
    _latest_tick: int | None = None
    max_ticks: int = 256

    def write(self, snapshot: MacroTickSnapshot) -> None:
        self._by_tick[snapshot.tick_id] = snapshot
        self._latest_tick = snapshot.tick_id
        if len(self._by_tick) > self.max_ticks:
            oldest = min(self._by_tick)
            del self._by_tick[oldest]

    def read(self, tick_id: int | None = None) -> MacroTickSnapshot | None:
        if tick_id is None:
            if self._latest_tick is None:
                return None
            return self._by_tick.get(self._latest_tick)
        return self._by_tick.get(tick_id)


def build_macro_state_dto(
    macro: MacroState,
    *,
    stress_cap: float,
    expansion_cap: float,
    est_recovery_eta_ticks: int | None,
) -> dict[str, object]:
    """Pure dict matching MacroStateDTO fields."""
    return {
        "regime": macro.regime.value,
        "stress": float(macro.stress),
        "expansion": float(macro.expansion),
        "stress_cap": float(stress_cap),
        "expansion_cap": float(expansion_cap),
        "episode_id": int(macro.episode_id),
        "ticks_in_episode": int(macro.ticks_in_episode),
        "peak_stress": float(macro.peak_stress),
        "peak_expansion": float(macro.peak_expansion),
        "est_recovery_eta_ticks": est_recovery_eta_ticks,
    }


def build_active_shock_dtos(
    active_shocks: tuple[ActiveShock, ...] | list[ActiveShock],
) -> list[dict[str, object]]:
    """Serialize active shocks; caller must exclude expired (remaining==0) via tick_down."""
    rows: list[dict[str, object]] = []
    for shock in active_shocks:
        scenario = shock.scenario
        if scenario is not None and scenario not in ("mild", "standard", "severe"):
            scenario = None
        rows.append(
            {
                "shock_type": shock.shock_type.value,
                "intensity": float(shock.intensity),
                "remaining_ticks": int(shock.remaining_ticks),
                "applied_at_tick": int(shock.applied_at_tick),
                "scenario": scenario,
            }
        )
    return rows


def write_macro_snapshot(
    memory: MacroSnapshotMemory,
    *,
    tick_id: int,
    macro: MacroState,
    active_shocks: tuple[ActiveShock, ...] | list[ActiveShock],
    ref_price: float | None,
    config: MacroDynamicsConfig,
) -> MacroTickSnapshot:
    """Build DTO dicts and store in memory (no disk)."""
    eta = estimate_recovery_eta(macro, config)
    snapshot = MacroTickSnapshot(
        tick_id=tick_id,
        macro_state=build_macro_state_dto(
            macro,
            stress_cap=config.stress_cap,
            expansion_cap=config.expansion_cap,
            est_recovery_eta_ticks=eta,
        ),
        active_shocks=build_active_shock_dtos(active_shocks),
        ref_price=ref_price,
    )
    memory.write(snapshot)
    return snapshot


def snapshot_to_json_bytes(snapshot: MacroTickSnapshot) -> bytes:
    """IPC-safe JSON encoding for mp.Array slot (Spec 014 §2.2)."""
    payload = {
        "tick_id": snapshot.tick_id,
        "macro_state": snapshot.macro_state,
        "active_shocks": snapshot.active_shocks,
        "ref_price": snapshot.ref_price,
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def snapshot_from_json_bytes(raw: bytes) -> MacroTickSnapshot | None:
    """Decode IPC slot; empty / invalid → None."""
    text = raw.split(b"\x00", 1)[0].decode("utf-8").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "macro_state" not in data:
        return None
    return MacroTickSnapshot(
        tick_id=int(data["tick_id"]),
        macro_state=dict(data["macro_state"]),
        active_shocks=list(data.get("active_shocks") or []),
        ref_price=(
            float(data["ref_price"]) if data.get("ref_price") is not None else None
        ),
    )


def write_macro_snapshot_ipc(
    ipc_array: object,
    snapshot: MacroTickSnapshot,
    *,
    capacity: int,
) -> None:
    """Atomically publish snapshot into shared char Array (null-padded)."""
    encoded = snapshot_to_json_bytes(snapshot)[: capacity - 1]
    padded = encoded + b"\x00" * (capacity - len(encoded))
    with ipc_array.get_lock():  # type: ignore[union-attr]
        ipc_array.raw = padded  # type: ignore[union-attr]


def clear_macro_snapshot_ipc(ipc_array: object, *, capacity: int) -> None:
    """Clear IPC slot (RESET / IDLE)."""
    padded = b"\x00" * capacity
    with ipc_array.get_lock():  # type: ignore[union-attr]
        ipc_array.raw = padded  # type: ignore[union-attr]


def read_macro_snapshot_ipc(ipc_array: object) -> MacroTickSnapshot | None:
    """Read latest snapshot from shared Array."""
    with ipc_array.get_lock():  # type: ignore[union-attr]
        raw = bytes(ipc_array.raw)  # type: ignore[union-attr]
    return snapshot_from_json_bytes(raw)
