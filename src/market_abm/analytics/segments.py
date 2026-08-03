# Spec 014 §7.1 — segment health aggregate (tick-time) + in-memory snapshot.
from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from market_abm.domain.constants import (
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_PVD_SEGMENT,
    COL_SCAR_FACTOR,
    PVD_SEGMENTS,
)

SEGMENT_ORDER: tuple[str, ...] = PVD_SEGMENTS


@dataclass
class SegmentSnapshotMemory:
    """In-memory precomputed SegmentRowDTO rows per tick (no disk I/O)."""

    _by_tick: dict[int, list[dict[str, object]]] = field(default_factory=dict)
    _latest_tick: int | None = None
    max_ticks: int = 256

    def write(self, tick_id: int, rows: list[dict[str, object]]) -> None:
        self._by_tick[tick_id] = rows
        self._latest_tick = tick_id
        if len(self._by_tick) > self.max_ticks:
            oldest = min(self._by_tick)
            del self._by_tick[oldest]

    def read(self, tick_id: int | None = None) -> list[dict[str, object]] | None:
        if tick_id is None:
            if self._latest_tick is None:
                return None
            return self._by_tick.get(self._latest_tick)
        return self._by_tick.get(tick_id)


def aggregate_segment_health(buyers_df: pl.DataFrame) -> list[dict[str, object]]:
    """
    Pure aggregate buyers → 3 SegmentRowDTO dicts (rich/standard/low).
    Call on worker tick — never inside REST handler.
    """
    required = {
        COL_PVD_SEGMENT,
        COL_BUDGET_EFFECTIVE,
        COL_BUDGET_BASELINE,
        COL_FREQ_EFFECTIVE,
        COL_SCAR_FACTOR,
        COL_IS_CHURNED,
    }
    missing = required - set(buyers_df.columns)
    if missing:
        raise ValueError(f"buyers_df missing columns for segment health: {sorted(missing)}")

    rows_out: list[dict[str, object]] = []
    for segment in SEGMENT_ORDER:
        part = buyers_df.filter(pl.col(COL_PVD_SEGMENT).cast(pl.String) == segment)
        n = int(part.height)
        if n == 0:
            rows_out.append(
                {
                    "segment": segment,
                    "n_buyers": 0,
                    "n_active": 0,
                    "mean_budget_effective": 0.0,
                    "mean_budget_baseline": 0.0,
                    "mean_freq_effective": 0.0,
                    "mean_scar_factor": 0.0,
                    "churn_share": 0.0,
                }
            )
            continue
        churned = part[COL_IS_CHURNED].to_numpy()
        n_churned = int(churned.sum())
        rows_out.append(
            {
                "segment": segment,
                "n_buyers": n,
                "n_active": n - n_churned,
                "mean_budget_effective": float(part[COL_BUDGET_EFFECTIVE].mean()),
                "mean_budget_baseline": float(part[COL_BUDGET_BASELINE].mean()),
                "mean_freq_effective": float(part[COL_FREQ_EFFECTIVE].mean()),
                "mean_scar_factor": float(part[COL_SCAR_FACTOR].mean()),
                "churn_share": float(n_churned) / float(n),
            }
        )
    return rows_out
