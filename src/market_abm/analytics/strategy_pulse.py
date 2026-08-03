# Spec 014 §6.1 — strategy pulse aggregate (avg demand_index by strategy + panic flag).
from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from market_abm.domain.constants import COL_DEMAND_INDEX, COL_STRATEGY_TYPE

STRATEGY_ORDER: tuple[str, ...] = ("MaxProfit", "MaxVolume", "RatingMaximizer")


@dataclass
class StrategyPulseMemory:
    """In-memory strategy pulse snapshots per tick."""

    _by_tick: dict[int, dict[str, object]] = field(default_factory=dict)
    _latest_tick: int | None = None
    max_ticks: int = 256

    def write(self, tick_id: int, payload: dict[str, object]) -> None:
        self._by_tick[tick_id] = payload
        self._latest_tick = tick_id
        if len(self._by_tick) > self.max_ticks:
            oldest = min(self._by_tick)
            del self._by_tick[oldest]

    def read(self, tick_id: int | None = None) -> dict[str, object] | None:
        if tick_id is None:
            if self._latest_tick is None:
                return None
            return self._by_tick.get(self._latest_tick)
        return self._by_tick.get(tick_id)


def aggregate_strategy_pulse(
    products_df: pl.DataFrame,
    *,
    panic_active: bool,
    tick_id: int,
) -> dict[str, object]:
    """Avg demand_index per strategy_type; always returns three strategies."""
    if COL_DEMAND_INDEX not in products_df.columns or COL_STRATEGY_TYPE not in products_df.columns:
        strategies = [
            {"strategy_type": name, "avg_demand_index": 0.0, "n_listings": 0}
            for name in STRATEGY_ORDER
        ]
        return {
            "tick_id": tick_id,
            "panic_active": panic_active,
            "strategies": strategies,
        }

    grouped = (
        products_df.with_columns(pl.col(COL_STRATEGY_TYPE).cast(pl.String))
        .group_by(COL_STRATEGY_TYPE)
        .agg(
            pl.col(COL_DEMAND_INDEX).mean().alias("avg_demand_index"),
            pl.len().alias("n_listings"),
        )
    )
    by_name = {
        str(row[COL_STRATEGY_TYPE]): row
        for row in grouped.iter_rows(named=True)
    }
    strategies: list[dict[str, object]] = []
    for name in STRATEGY_ORDER:
        row = by_name.get(name)
        if row is None:
            strategies.append(
                {"strategy_type": name, "avg_demand_index": 0.0, "n_listings": 0}
            )
        else:
            strategies.append(
                {
                    "strategy_type": name,
                    "avg_demand_index": float(row["avg_demand_index"] or 0.0),
                    "n_listings": int(row["n_listings"]),
                }
            )
    return {
        "tick_id": tick_id,
        "panic_active": bool(panic_active),
        "strategies": strategies,
    }
