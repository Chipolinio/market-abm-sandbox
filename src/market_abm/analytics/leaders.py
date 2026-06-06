# Назначение файла: market-leaders и demand-matrix query-side (Slice 8.3).
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from market_abm.analytics.store import AnalyticsStore, _TICK_ID_FROM_FILENAME
from market_abm.domain.constants import COL_DEMAND_INDEX, COL_PRICE, COL_RATING_VALUE
from market_abm.domain.constants import (
    ALGORITHM_TYPES,
    COL_IS_BANKRUPT,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_WORKING_CAPITAL,
    LOGIC_STATUS_BANKRUPT,
    LOGIC_STATUS_DUMPING,
    LOGIC_STATUS_ROI,
    LOGIC_STATUS_RULE,
    SELLERS_STATE_COLUMNS,
)


def _sellers_state_at_tick(store: AnalyticsStore, tick_id: int) -> pl.DataFrame | None:
    run_root = store._run_root
    for candidate in range(tick_id, -1, -1):
        path = run_root / "sellers_state" / f"tick_{candidate:06d}.parquet"
        if path.is_file():
            return pl.read_parquet(path).select(list(SELLERS_STATE_COLUMNS))
    return None


def _resolved_tick_id(store: AnalyticsStore, tick_id: int, subdir: str) -> int:
    """Nearest persisted tick_id <= requested (worker counter is next tick to run)."""
    run_root = store._run_root
    for candidate in range(tick_id, -1, -1):
        path = run_root / subdir / f"tick_{candidate:06d}.parquet"
        if path.is_file():
            return candidate
    return tick_id


def _algorithm_type_for_seller(seller_id: int) -> str:
    return ALGORITHM_TYPES[seller_id % len(ALGORITHM_TYPES)]


def _logic_status_for_seller(seller_id: int, *, is_bankrupt: bool) -> str:
    if is_bankrupt:
        return LOGIC_STATUS_BANKRUPT
    algo = _algorithm_type_for_seller(seller_id)
    if algo == "CB":
        return LOGIC_STATUS_ROI
    if algo == "REPR":
        return LOGIC_STATUS_DUMPING
    return LOGIC_STATUS_RULE


def _inventory_by_seller(store: AnalyticsStore, tick_id: int) -> dict[int, int]:
    products = store.products_snapshot_at_tick(tick_id)
    if products.height == 0:
        return {}
    counts = products.group_by(COL_SELLER_ID).len()
    return {int(row[COL_SELLER_ID]): int(row["len"]) for row in counts.iter_rows(named=True)}


def query_market_leaders(
    store: AnalyticsStore,
    tick_id: int,
    *,
    limit: int = 5,
) -> dict[str, object]:
    """Top-N селлеров по working_capital DESC (backend sort)."""
    run_id = store._run_id_from_manifest()
    resolved_tick = _resolved_tick_id(store, tick_id, "sellers_state")
    sellers_state = _sellers_state_at_tick(store, tick_id)
    if sellers_state is None or sellers_state.height == 0:
        return {"run_id": run_id, "tick_id": tick_id, "leaders": []}

    empty_revenue = pl.DataFrame(
        {
            COL_SELLER_ID: pl.Series([], dtype=pl.Int32),
            "tick_revenue": pl.Series([], dtype=pl.Float64),
        }
    )
    empty_cumulative = pl.DataFrame(
        {
            COL_SELLER_ID: pl.Series([], dtype=pl.Int32),
            "cumulative_revenue": pl.Series([], dtype=pl.Float64),
        }
    )

    if store._has_parquet_files("transactions"):
        tx_glob = str(store._run_root / "transactions" / "tick_*.parquet")
        tick_revenue_df = store._query_pl(
            """
            SELECT seller_id, SUM(price_paid)::DOUBLE AS tick_revenue
            FROM read_parquet(?)
            WHERE tick_id = ?
            GROUP BY seller_id
            """,
            [tx_glob, resolved_tick],
        )
        cumulative_df = store._query_pl(
            """
            SELECT seller_id, SUM(price_paid)::DOUBLE AS cumulative_revenue
            FROM read_parquet(?)
            WHERE tick_id <= ?
            GROUP BY seller_id
            """,
            [tx_glob, resolved_tick],
        )
    else:
        tick_revenue_df = empty_revenue
        cumulative_df = empty_cumulative

    inventory = _inventory_by_seller(store, resolved_tick)

    joined = (
        sellers_state.join(tick_revenue_df, on=COL_SELLER_ID, how="left")
        .join(cumulative_df, on=COL_SELLER_ID, how="left")
        .with_columns(
            pl.col("tick_revenue").fill_null(0.0),
            pl.col("cumulative_revenue").fill_null(0.0),
        )
        .sort(COL_WORKING_CAPITAL, descending=True)
        .head(limit)
    )

    leaders = [
        {
            "seller_id": int(row[COL_SELLER_ID]),
            "working_capital": float(row[COL_WORKING_CAPITAL]),
            "tick_revenue": float(row["tick_revenue"]),
            "cumulative_revenue": float(row["cumulative_revenue"]),
            "is_bankrupt": bool(row[COL_IS_BANKRUPT]),
            "algorithm_type": _algorithm_type_for_seller(int(row[COL_SELLER_ID])),
            "inventory_stock": inventory.get(int(row[COL_SELLER_ID]), 0),
            "logic_status": _logic_status_for_seller(
                int(row[COL_SELLER_ID]),
                is_bankrupt=bool(row[COL_IS_BANKRUPT]),
            ),
        }
        for row in joined.iter_rows(named=True)
    ]
    return {"run_id": run_id, "tick_id": resolved_tick, "leaders": leaders}


def _decile_bins(values: list[float], grid_size: int) -> list[int]:
    """Map values to decile indices [0, grid_size-1]; ties share the same market bin."""
    if not values:
        return []
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 1:
        return [grid_size // 2]
    edges = np.quantile(arr, np.linspace(0.0, 1.0, grid_size + 1))
    edges = np.maximum.accumulate(edges)
    bins = np.clip(np.digitize(arr, edges[1:-1], right=False), 0, grid_size - 1)
    return [int(b) for b in bins]


def query_demand_matrix(
    store: AnalyticsStore,
    tick_id: int,
    *,
    grid_size: int = 10,
) -> dict[str, object]:
    """
    10×10 heatmap: mean demand_index by price decile (col) × rating decile (row).

    row 0 (top) = highest rating tier; col 0 (left) = cheapest price tier.
    """
    run_id = store._run_id_from_manifest()
    n_cells = grid_size * grid_size

    def _empty_cells() -> list[dict[str, object]]:
        return [
            {"row": row, "col": col, "density": 0.0}
            for row in range(grid_size)
            for col in range(grid_size)
        ]

    if not store._has_parquet_files("products_snapshots"):
        return {
            "run_id": run_id,
            "tick_id": tick_id,
            "grid_size": grid_size,
            "cells": _empty_cells(),
        }

    resolved_tick = _resolved_tick_id(store, tick_id, "products_snapshots")
    sql = f"""
        WITH snap AS (
            SELECT
                {_TICK_ID_FROM_FILENAME} AS snap_tick,
                {COL_PRICE}::DOUBLE AS price,
                {COL_RATING_VALUE}::DOUBLE AS rating_value,
                {COL_DEMAND_INDEX}::DOUBLE AS demand_index
            FROM read_parquet(?, filename=true)
            WHERE {_TICK_ID_FROM_FILENAME} <= ?
        ),
        latest AS (
            SELECT MAX(snap_tick) AS snap_tick FROM snap
        )
        SELECT s.price, s.rating_value, s.demand_index
        FROM snap s
        INNER JOIN latest l ON s.snap_tick = l.snap_tick
    """
    df = store._query_pl(sql, [store._products_glob(), tick_id])
    if df.height == 0:
        return {
            "run_id": run_id,
            "tick_id": resolved_tick,
            "grid_size": grid_size,
            "cells": _empty_cells(),
        }

    prices = [float(v) for v in df[COL_PRICE].to_list()]
    ratings = [float(v) for v in df["rating_value"].to_list()]
    demands = [float(v) for v in df[COL_DEMAND_INDEX].to_list()]

    price_bins = _decile_bins(prices, grid_size)
    rating_bins = _decile_bins(ratings, grid_size)

    sums = np.zeros((grid_size, grid_size), dtype=np.float64)
    counts = np.zeros((grid_size, grid_size), dtype=np.int64)
    for demand, price_bin, rating_bin in zip(demands, price_bins, rating_bins, strict=True):
        row = (grid_size - 1) - rating_bin
        col = price_bin
        sums[row, col] += demand
        counts[row, col] += 1

    raw_densities = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    positive = raw_densities[raw_densities > 0.0]
    max_val = float(positive.max()) if positive.size else 0.0
    min_val = float(positive.min()) if positive.size else 0.0
    span = max_val - min_val

    cells: list[dict[str, object]] = []
    for row in range(grid_size):
        for col in range(grid_size):
            raw = float(raw_densities[row, col])
            if counts[row, col] == 0:
                density = 0.0
            elif span > 0.0:
                density = (raw - min_val) / span
            elif raw > 0.0:
                density = 1.0
            else:
                density = 0.0
            cells.append({"row": row, "col": col, "density": density})

    return {
        "run_id": run_id,
        "tick_id": resolved_tick,
        "grid_size": grid_size,
        "cells": cells,
    }


def write_sellers_state_snapshot(run_root: Path, tick_id: int, sellers_state_df: pl.DataFrame) -> None:
    """Тестовый/воркерный helper: пишет sellers_state parquet (8.4 integration)."""
    out_dir = Path(run_root) / "sellers_state"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tick_{tick_id:06d}.parquet"
    sellers_state_df.select(list(SELLERS_STATE_COLUMNS)).write_parquet(path)
