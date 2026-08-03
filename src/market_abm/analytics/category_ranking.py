# Spec 014 §7.2 — per-category ranking aggregate (analytics query, RankingConfig weights).
from __future__ import annotations

import polars as pl

from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_LISTING_ID,
    COL_PRICE,
    COL_RANKING_SCORE,
)
from market_abm.simulation.ranking import compute_ranking_scores

_SALES_COL = "sales_volume_window"
_DEFAULT_TOP_N = 3


def aggregate_category_ranking(
    products_df: pl.DataFrame,
    *,
    ranking: RankingConfig | None = None,
    top_n: int = _DEFAULT_TOP_N,
) -> list[dict[str, object]]:
    """
    Per category_id: median score, median price, sales sum, top listing ids.

    Recomputes score via RankingConfig weights (Spec 014 §7.2 / §17) — does not
    require persisted ranking_score in parquet.
    """
    cfg = ranking or RankingConfig()
    if products_df.height == 0 or COL_CATEGORY_ID not in products_df.columns:
        return []

    # Keep sales for aggregation even when compute_ranking_scores drops the helper.
    had_sales = _SALES_COL in products_df.columns
    ranked = compute_ranking_scores(products_df, cfg)
    if not had_sales:
        ranked = ranked.with_columns(pl.lit(0.0).alias(_SALES_COL))
    elif _SALES_COL not in ranked.columns:
        ranked = ranked.join(
            products_df.select([COL_LISTING_ID, _SALES_COL]),
            on=COL_LISTING_ID,
            how="left",
        )

    rows_out: list[dict[str, object]] = []
    for category_id in sorted(ranked[COL_CATEGORY_ID].unique().to_list()):
        part = ranked.filter(pl.col(COL_CATEGORY_ID) == category_id)
        n = int(part.height)
        median_score = float(part[COL_RANKING_SCORE].median())
        median_price = float(part[COL_PRICE].median())
        sales_sum = float(part[_SALES_COL].fill_null(0.0).sum())
        top = (
            part.sort(COL_RANKING_SCORE, descending=True)
            .head(max(1, int(top_n)))[COL_LISTING_ID]
            .to_list()
        )
        rows_out.append(
            {
                "category_id": int(category_id),
                "n_listings": n,
                "median_score": median_score,
                "median_price": median_price,
                "sales_window_sum": sales_sum,
                "top_listing_ids": [int(x) for x in top],
            }
        )
    return rows_out
