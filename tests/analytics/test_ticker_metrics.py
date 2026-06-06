# Назначение файла: query_ticker_metrics (Slice 8.3).
from __future__ import annotations

from pathlib import Path

import polars as pl

from market_abm.analytics.store import AnalyticsStore
from market_abm.analytics.ticker import query_ticker_metrics
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
)
from tests.analytics.test_analytics_store import _persist_run, _products_snapshot, _tx_rows


def test_query_ticker_metrics_cumulative_gmv_and_index(tmp_path: Path) -> None:
    ticks: list[tuple[pl.DataFrame, pl.DataFrame]] = []
    for t in range(3):
        tx = _tx_rows(
            [
                {
                    COL_TICK_ID: t,
                    COL_BUYER_ID: 0,
                    COL_LISTING_ID: 0,
                    COL_SELLER_ID: 0,
                    COL_PRICE_PAID: 100.0 * (t + 1),
                    COL_UNIT_COST: 20.0,
                    COL_GROSS_MARGIN: 80.0,
                },
            ]
        )
        products = _products_snapshot(2, prices=[100.0 * (t + 1), 200.0])
        ticks.append((tx, products))

    run_root = _persist_run(tmp_path, run_id="ticker-run", ticks=ticks)
    store = AnalyticsStore(run_root)
    try:
        metrics = query_ticker_metrics(store, tick_id=2)
    finally:
        store.close()

    assert metrics["current_tick"] == 2
    assert metrics["total_market_gmv"] == 600.0
    assert metrics["active_sellers_count"] == 2
    assert metrics["total_non_bankrupt_sellers"] == 2
    assert metrics["market_price_index"] > 1.0
