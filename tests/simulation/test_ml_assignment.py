# Spec 015 slice 15.3 — ml_seller_share assignment (pure, deterministic).
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import (
    COL_CAPITAL,
    COL_MARGIN_FLOOR,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_USES_ML,
)
from market_abm.simulation.ml_assignment import assign_ml_sellers


def _sellers(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            COL_CAPITAL: [100.0] * n,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col(COL_CAPITAL).cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def test_15_3_t1_share_0_all_rules() -> None:
    """15.3-T1: share=0 → uses_ml all False."""
    out = assign_ml_sellers(_sellers(10), share=0.0, seed=42)
    assert COL_USES_ML in out.columns
    assert out[COL_USES_ML].to_list() == [False] * 10


def test_15_3_t2_share_1_all_ml() -> None:
    """15.3-T2: share=1 → uses_ml all True."""
    out = assign_ml_sellers(_sellers(10), share=1.0, seed=42)
    assert out[COL_USES_ML].to_list() == [True] * 10


def test_15_3_t3_share_0_25_count() -> None:
    """15.3-T3: n_sellers=100, share=0.25 → exactly 25 True."""
    out = assign_ml_sellers(_sellers(100), share=0.25, seed=7)
    assert int(out[COL_USES_ML].sum()) == 25


def test_15_3_t4_assignment_seed_stable() -> None:
    """15.3-T4: same seed → identical mask."""
    a = assign_ml_sellers(_sellers(40), share=0.5, seed=99)
    b = assign_ml_sellers(_sellers(40), share=0.5, seed=99)
    assert a[COL_USES_ML].to_list() == b[COL_USES_ML].to_list()
    c = assign_ml_sellers(_sellers(40), share=0.5, seed=100)
    assert a[COL_USES_ML].to_list() != c[COL_USES_ML].to_list()


def test_seller_id_order_is_nested_dose_response() -> None:
    """seller_id order: share increases expand ML set; seller 0 always early."""
    low = assign_ml_sellers(_sellers(8), share=0.25, seed=1, order="seller_id")
    mid = assign_ml_sellers(_sellers(8), share=0.5, seed=1, order="seller_id")
    high = assign_ml_sellers(_sellers(8), share=0.75, seed=1, order="seller_id")
    assert int(low[COL_USES_ML].sum()) == 2
    assert int(mid[COL_USES_ML].sum()) == 4
    assert int(high[COL_USES_ML].sum()) == 6
    low_ids = set(low.filter(pl.col(COL_USES_ML))[COL_SELLER_ID].to_list())
    mid_ids = set(mid.filter(pl.col(COL_USES_ML))[COL_SELLER_ID].to_list())
    high_ids = set(high.filter(pl.col(COL_USES_ML))[COL_SELLER_ID].to_list())
    assert low_ids == {0, 1}
    assert low_ids < mid_ids < high_ids
