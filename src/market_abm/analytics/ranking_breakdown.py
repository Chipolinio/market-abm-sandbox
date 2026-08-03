# Spec 014 §6.2 — ranking score breakdown for one seller's primary listing.
from __future__ import annotations

import math

import polars as pl

from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_PRICE,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)


def compute_listing_ranking_breakdown(
    products_df: pl.DataFrame,
    *,
    seller_id: int,
    ranking: RankingConfig | None = None,
    sales_volume_by_listing: dict[int, float] | None = None,
) -> dict[str, object] | None:
    """
    Score = w1·Rating + w2·(Pcat/P) + w3·log1p(Sales) for seller's first listing.
    Returns None if seller has no listing.
    """
    cfg = ranking or RankingConfig()
    if COL_SELLER_ID not in products_df.columns:
        return None
    part = products_df.filter(pl.col(COL_SELLER_ID) == int(seller_id))
    if part.height == 0:
        return None
    row = part.row(0, named=True)
    listing_id = int(row.get("listing_id", -1))
    rating = float(row.get(COL_RATING_VALUE, 0.0) or 0.0)
    price = float(row.get(COL_PRICE, 0.0) or 0.0)
    category_id = row.get(COL_CATEGORY_ID)

    if category_id is not None and COL_CATEGORY_ID in products_df.columns and price > 0:
        cat_prices = products_df.filter(
            pl.col(COL_CATEGORY_ID) == category_id
        )[COL_PRICE]
        p_cat = float(cat_prices.median()) if cat_prices.len() > 0 else price
    else:
        p_cat = price if price > 0 else 1.0

    price_term = (p_cat / price) if price > 0 else 0.0
    sales = 0.0
    if sales_volume_by_listing is not None:
        sales = float(sales_volume_by_listing.get(listing_id, 0.0))
    sales_term = math.log1p(sales)

    term_rating = cfg.w1 * rating
    term_price = cfg.w2 * price_term
    term_sales = cfg.w3 * sales_term
    score = term_rating + term_price + term_sales

    return {
        "seller_id": int(seller_id),
        "listing_id": listing_id,
        "w1": float(cfg.w1),
        "w2": float(cfg.w2),
        "w3": float(cfg.w3),
        "rating": rating,
        "price_term": price_term,
        "sales_term": sales_term,
        "term_rating": term_rating,
        "term_price": term_price,
        "term_sales": term_sales,
        "score": score,
    }
