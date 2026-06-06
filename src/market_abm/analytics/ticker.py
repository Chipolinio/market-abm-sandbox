# Назначение файла: query_ticker_metrics для WS ribbon (Slice 8.3).
from __future__ import annotations

import polars as pl

from market_abm.analytics.store import AnalyticsStore
from market_abm.domain.constants import COL_IS_BANKRUPT, COL_SELLER_ID


def query_ticker_metrics(
    store: AnalyticsStore,
    tick_id: int,
    *,
    sellers_state_df: pl.DataFrame | None = None,
) -> dict[str, int | float]:
    """
    Агрегаты верхней ленты терминала.
    sellers_state_df — опциональный snapshot воркера; иначе все селлеры из products non-bankrupt.
    """
    products = store.products_snapshot_at_tick(tick_id)
    active_seller_ids: set[int] = set()
    if products.height > 0:
        active_seller_ids = set(products[COL_SELLER_ID].unique().to_list())

    bankrupt_ids: set[int] = set()
    if sellers_state_df is not None and sellers_state_df.height > 0:
        bankrupt_ids = set(
            sellers_state_df.filter(pl.col(COL_IS_BANKRUPT))[COL_SELLER_ID].to_list()
        )
        non_bankrupt_ids = set(
            sellers_state_df.filter(~pl.col(COL_IS_BANKRUPT))[COL_SELLER_ID].to_list()
        )
        total_non_bankrupt = len(non_bankrupt_ids)
        active_sellers_count = len(active_seller_ids - bankrupt_ids)
    else:
        total_non_bankrupt = len(active_seller_ids)
        active_sellers_count = total_non_bankrupt

    total_market_gmv = 0.0
    gmv_df = store.gmv_by_tick()
    if gmv_df.height > 0:
        total_market_gmv = float(
            gmv_df.filter(pl.col("tick_id") <= tick_id)["gmv"].sum()
        )

    baseline_agg = store.query_market_aggregate(0)
    current_agg = store.query_market_aggregate(tick_id)
    baseline_mean = float(baseline_agg["mean_price"])
    current_mean = float(current_agg["mean_price"])
    if baseline_mean == 0.0:
        market_price_index = 1.0
    else:
        market_price_index = current_mean / baseline_mean

    return {
        "active_sellers_count": active_sellers_count,
        "total_non_bankrupt_sellers": total_non_bankrupt,
        "total_market_gmv": total_market_gmv,
        "market_price_index": market_price_index,
        "current_tick": tick_id,
    }
