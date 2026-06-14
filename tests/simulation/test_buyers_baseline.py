# Spec 010 §10.1 — ensure_budget_baseline для legacy buyers_df без колонки.
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import COL_BUDGET, COL_BUDGET_BASELINE, COL_BUYER_ID
from market_abm.simulation.buyers_baseline import ensure_budget_baseline


def test_ensure_budget_baseline_noop_when_column_present() -> None:
    buyers = pl.DataFrame(
        {
            COL_BUYER_ID: [0, 1],
            COL_BUDGET: [100.0, 200.0],
            COL_BUDGET_BASELINE: [100.0, 200.0],
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BUDGET_BASELINE).cast(pl.Float32),
    )
    out = ensure_budget_baseline(buyers)
    assert out.equals(buyers)


def test_ensure_budget_baseline_aliases_budget_when_missing() -> None:
    buyers = pl.DataFrame(
        {COL_BUYER_ID: [0], COL_BUDGET: [150.0]}
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
    )
    out = ensure_budget_baseline(buyers)
    assert COL_BUDGET_BASELINE in out.columns
    assert out[COL_BUDGET_BASELINE].equals(out[COL_BUDGET])
