# Spec 014 §7.2 / §13.5 — category ranking aggregate + REST (slice 14.5).
from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi.testclient import TestClient

from market_abm.analytics.category_ranking import aggregate_category_ranking
from market_abm.api.app import create_app
from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_LISTING_ID,
    COL_PRICE,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)


def _products_two_categories() -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: [10, 11, 20, 21, 22],
            COL_SELLER_ID: [1, 2, 3, 4, 5],
            COL_CATEGORY_ID: [0, 0, 1, 1, 1],
            COL_PRICE: [100.0, 120.0, 50.0, 60.0, 70.0],
            COL_RATING_VALUE: [0.9, 0.5, 0.8, 0.7, 0.6],
            "sales_volume_window": [5.0, 1.0, 10.0, 2.0, 0.0],
        }
    )


def test_14_5_aggregate_category_ranking_rows() -> None:
    rows = aggregate_category_ranking(
        _products_two_categories(),
        ranking=RankingConfig(),
    )
    assert len(rows) >= 1
    assert [r["category_id"] for r in rows] == [0, 1]
    cat0 = rows[0]
    assert cat0["n_listings"] == 2
    assert cat0["median_score"] > 0.0
    assert cat0["median_price"] == pytest.approx(110.0)
    assert cat0["sales_window_sum"] == pytest.approx(6.0)
    assert isinstance(cat0["top_listing_ids"], list)
    assert len(cat0["top_listing_ids"]) >= 1


def test_14_5_t1_category_ranking_endpoint_rows() -> None:
    products = _products_two_categories()
    worker = MagicMock()
    worker.state = MagicMock(name="IDLE")
    app = create_app(worker=worker)
    app.state.ranking_products = products
    client = TestClient(app)

    resp = client.get("/api/v1/analytics/category-ranking?tick_id=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tick_id"] == 0
    assert len(body["rows"]) >= 1
    assert {r["category_id"] for r in body["rows"]} == {0, 1}
    for row in body["rows"]:
        assert "median_score" in row
        assert "n_listings" in row
        assert "median_price" in row
        assert "sales_window_sum" in row
        assert "top_listing_ids" in row
