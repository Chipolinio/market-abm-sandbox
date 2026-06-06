# Назначение файла: market-leaders и demand-matrix query-side (Slice 8.3).
from __future__ import annotations

from pathlib import Path

import polars as pl

from market_abm.analytics.store import AnalyticsStore
from market_abm.domain.constants import (
    COL_IS_BANKRUPT,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_WORKING_CAPITAL,
    SELLERS_STATE_COLUMNS,
)


def _sellers_state_at_tick(store: AnalyticsStore, tick_id: int) -> pl.DataFrame | None:
    run_root = store._run_root
    path = run_root / "sellers_state" / f"tick_{tick_id:06d}.parquet"
    if path.is_file():
        return pl.read_parquet(path).select(list(SELLERS_STATE_COLUMNS))
    return None


def query_market_leaders(
    store: AnalyticsStore,
    tick_id: int,
    *,
    limit: int = 5,
) -> dict[str, object]:
    """Top-N селлеров по working_capital DESC (backend sort)."""
    run_id = store._run_id_from_manifest()
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
            [tx_glob, tick_id],
        )
        cumulative_df = store._query_pl(
            """
            SELECT seller_id, SUM(price_paid)::DOUBLE AS cumulative_revenue
            FROM read_parquet(?)
            WHERE tick_id <= ?
            GROUP BY seller_id
            """,
            [tx_glob, tick_id],
        )
    else:
        tick_revenue_df = empty_revenue
        cumulative_df = empty_cumulative

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
        }
        for row in joined.iter_rows(named=True)
    ]
    return {"run_id": run_id, "tick_id": tick_id, "leaders": leaders}


def query_demand_matrix(
    store: AnalyticsStore,
    tick_id: int,
    *,
    grid_size: int = 10,
) -> dict[str, object]:
    """v1 placeholder: uniform zero density grid 10×10."""
    run_id = store._run_id_from_manifest()
    cells = [
        {"row": row, "col": col, "density": 0.0}
        for row in range(grid_size)
        for col in range(grid_size)
    ]
    return {
        "run_id": run_id,
        "tick_id": tick_id,
        "grid_size": grid_size,
        "cells": cells,
    }


def write_sellers_state_snapshot(run_root: Path, tick_id: int, sellers_state_df: pl.DataFrame) -> None:
    """Тестовый/воркерный helper: пишет sellers_state parquet (8.4 integration)."""
    out_dir = Path(run_root) / "sellers_state"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"tick_{tick_id:06d}.parquet"
    sellers_state_df.select(list(SELLERS_STATE_COLUMNS)).write_parquet(path)
