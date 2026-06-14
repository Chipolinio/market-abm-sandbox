# Stub buyers/sellers для init_run_directory → write_reference_snapshots.
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_PVD_SEGMENT,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
)


def stub_buyers_df(
    buyer_ids: list[int],
    *,
    pvd_segments: list[str] | None = None,
) -> pl.DataFrame:
    if pvd_segments is None:
        pvd_segments = ["standard"] * len(buyer_ids)
    return pl.DataFrame(
        {COL_BUYER_ID: buyer_ids, COL_PVD_SEGMENT: pvd_segments}
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_PVD_SEGMENT).cast(pl.Categorical),
    )


def stub_sellers_df(
    seller_ids: list[int],
    *,
    strategy_types: list[str] | None = None,
) -> pl.DataFrame:
    if strategy_types is None:
        strategy_types = ["MaxProfit"] * len(seller_ids)
    return pl.DataFrame(
        {COL_SELLER_ID: seller_ids, COL_STRATEGY_TYPE: strategy_types}
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
    )
