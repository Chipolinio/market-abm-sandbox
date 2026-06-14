# Назначение файла: market-leaders и demand-matrix query-side (Slice 8.3 / Spec 011 §6).
from __future__ import annotations

from pathlib import Path
from typing import Literal

import numpy as np
import polars as pl

from market_abm.analytics.persist import reference_buyers_path, reference_sellers_path
from market_abm.analytics.store import AnalyticsStore
from market_abm.domain.constants import (
    COL_IS_BANKRUPT,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_WORKING_CAPITAL,
    DEMAND_MATRIX_PVD_ORDER,
    DEMAND_MATRIX_STRATEGY_ORDER,
    LOGIC_STATUS_BANKRUPT,
    LOGIC_STATUS_RULE,
    SELLERS_STATE_COLUMNS,
    STRATEGY_ALGORITHM_TYPE,
    STRATEGY_LOGIC_STATUS,
)

LeaderRankBy = Literal["working_capital", "tick_revenue", "cumulative_revenue"]


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


def _reference_sellers(store: AnalyticsStore) -> pl.DataFrame | None:
    path = reference_sellers_path(store._run_root)
    if not path.is_file():
        return None
    return pl.read_parquet(path).select([COL_SELLER_ID, COL_STRATEGY_TYPE])


def _algorithm_type_for_strategy(strategy: str) -> str:
    return STRATEGY_ALGORITHM_TYPE.get(strategy, "RULE")


def _logic_status_for_strategy(strategy: str, *, is_bankrupt: bool) -> str:
    if is_bankrupt:
        return LOGIC_STATUS_BANKRUPT
    return STRATEGY_LOGIC_STATUS.get(strategy, LOGIC_STATUS_RULE)


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
    rank_by: LeaderRankBy = "tick_revenue",
) -> dict[str, object]:
    """Top-N селлеров; default rank_by=tick_revenue (Spec 011 §6.2)."""
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
    reference_sellers = _reference_sellers(store)

    joined = (
        sellers_state.join(tick_revenue_df, on=COL_SELLER_ID, how="left")
        .join(cumulative_df, on=COL_SELLER_ID, how="left")
        .with_columns(
            pl.col("tick_revenue").fill_null(0.0),
            pl.col("cumulative_revenue").fill_null(0.0),
        )
    )
    if reference_sellers is not None:
        joined = joined.join(
            reference_sellers.with_columns(pl.col(COL_STRATEGY_TYPE).cast(pl.String)),
            on=COL_SELLER_ID,
            how="left",
        )
    else:
        joined = joined.with_columns(pl.lit(None, dtype=pl.String).alias(COL_STRATEGY_TYPE))

    sort_col = {
        "working_capital": COL_WORKING_CAPITAL,
        "tick_revenue": "tick_revenue",
        "cumulative_revenue": "cumulative_revenue",
    }[rank_by]
    joined = joined.sort(sort_col, descending=True).head(limit)

    leaders = [
        {
            "seller_id": int(row[COL_SELLER_ID]),
            "working_capital": float(row[COL_WORKING_CAPITAL]),
            "tick_revenue": float(row["tick_revenue"]),
            "cumulative_revenue": float(row["cumulative_revenue"]),
            "is_bankrupt": bool(row[COL_IS_BANKRUPT]),
            "strategy_type": (
                str(row[COL_STRATEGY_TYPE]) if row[COL_STRATEGY_TYPE] is not None else None
            ),
            "algorithm_type": _algorithm_type_for_strategy(
                str(row[COL_STRATEGY_TYPE]) if row[COL_STRATEGY_TYPE] is not None else ""
            ),
            "inventory_stock": inventory.get(int(row[COL_SELLER_ID]), 0),
            "logic_status": _logic_status_for_strategy(
                str(row[COL_STRATEGY_TYPE]) if row[COL_STRATEGY_TYPE] is not None else "",
                is_bankrupt=bool(row[COL_IS_BANKRUPT]),
            ),
        }
        for row in joined.iter_rows(named=True)
    ]
    return {"run_id": run_id, "tick_id": resolved_tick, "leaders": leaders}


def _empty_strategy_pvd_cells() -> list[dict[str, object]]:
    return [
        {"row": row_idx, "col": col_idx, "density": 0.0}
        for row_idx in range(len(DEMAND_MATRIX_PVD_ORDER))
        for col_idx in range(len(DEMAND_MATRIX_STRATEGY_ORDER))
    ]


def _has_reference_snapshots(store: AnalyticsStore) -> bool:
    run_root = store._run_root
    return reference_buyers_path(run_root).is_file() and reference_sellers_path(run_root).is_file()


def query_demand_matrix(
    store: AnalyticsStore,
    tick_id: int,
) -> dict[str, object]:
    """
    Strategy × buyer-segment heatmap: transaction counts per cell.

    Col (X): seller strategy_type — MaxProfit / MaxVolume / RatingMaximizer.
    Row (Y): buyer pvd_segment — rich (top) → low (bottom, price-sensitive).
    Density: normalized share of tick transactions in each cell [0, 1].
    """
    run_id = store._run_id_from_manifest()
    row_labels = list(DEMAND_MATRIX_PVD_ORDER)
    col_labels = list(DEMAND_MATRIX_STRATEGY_ORDER)
    n_rows = len(row_labels)
    n_cols = len(col_labels)
    grid_size = max(n_rows, n_cols)

    base = {
        "run_id": run_id,
        "tick_id": tick_id,
        "grid_size": grid_size,
        "row_count": n_rows,
        "col_count": n_cols,
        "x_labels": col_labels,
        "y_labels": row_labels,
        "axis_x": "strategy_type",
        "axis_y": "pvd_segment",
        "cells": _empty_strategy_pvd_cells(),
    }

    if not _has_reference_snapshots(store) or not store._has_parquet_files("transactions"):
        return base

    resolved_tick = _resolved_tick_id(store, tick_id, "transactions")
    buyers_path = str(reference_buyers_path(store._run_root))
    sellers_path = str(reference_sellers_path(store._run_root))
    tx_glob = str(store._run_root / "transactions" / "tick_*.parquet")

    counts_df = store._query_pl(
        """
        SELECT
            CAST(b.pvd_segment AS VARCHAR) AS pvd_segment,
            CAST(s.strategy_type AS VARCHAR) AS strategy_type,
            COUNT(*)::BIGINT AS txn_count
        FROM read_parquet(?) AS tx
        INNER JOIN read_parquet(?) AS b ON tx.buyer_id = b.buyer_id
        INNER JOIN read_parquet(?) AS s ON tx.seller_id = s.seller_id
        WHERE tx.tick_id = ?
        GROUP BY 1, 2
        """,
        [tx_glob, buyers_path, sellers_path, resolved_tick],
    )

    row_index = {label: idx for idx, label in enumerate(row_labels)}
    col_index = {label: idx for idx, label in enumerate(col_labels)}
    raw_counts = np.zeros((n_rows, n_cols), dtype=np.float64)

    if counts_df.height > 0:
        for row in counts_df.iter_rows(named=True):
            pvd = str(row["pvd_segment"])
            strategy = str(row["strategy_type"])
            if pvd not in row_index or strategy not in col_index:
                continue
            raw_counts[row_index[pvd], col_index[strategy]] = float(row["txn_count"])

    total_tx = float(raw_counts.sum())
    max_cell = float(raw_counts.max()) if raw_counts.size else 0.0

    cells: list[dict[str, object]] = []
    for row_idx in range(n_rows):
        for col_idx in range(n_cols):
            count = raw_counts[row_idx, col_idx]
            if count <= 0.0:
                density = 0.0
            elif total_tx > 0.0:
                density = count / total_tx
            elif max_cell > 0.0:
                density = count / max_cell
            else:
                density = 0.0
            cells.append({"row": row_idx, "col": col_idx, "density": density})

    return {
        **base,
        "tick_id": resolved_tick,
        "cells": cells,
    }


def write_sellers_state_snapshot(run_root: Path, tick_id: int, sellers_state_df: pl.DataFrame) -> None:
    """Тестовый/воркерный helper: пишет sellers_state parquet (8.4 integration)."""
    out_dir = Path(run_root) / "sellers_state"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tick_{tick_id:06d}.parquet"
    sellers_state_df.select(list(SELLERS_STATE_COLUMNS)).write_parquet(path)
