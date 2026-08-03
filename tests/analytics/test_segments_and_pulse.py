# Spec 014 §13.4 — segments / strategy-pulse / ranking breakdown (slice 14.4).
from __future__ import annotations

from unittest.mock import MagicMock

import polars as pl
import pytest
from fastapi.testclient import TestClient

from market_abm.analytics.ranking_breakdown import compute_listing_ranking_breakdown
from market_abm.analytics.segments import (
    SegmentSnapshotMemory,
    aggregate_segment_health,
)
from market_abm.analytics.strategy_pulse import (
    StrategyPulseMemory,
    aggregate_strategy_pulse,
)
from market_abm.api.app import create_app
from market_abm.config.ranking import RankingConfig
from market_abm.domain.constants import (
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_DEMAND_INDEX,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PVD_SEGMENT,
    COL_RATING_VALUE,
    COL_SCAR_FACTOR,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
)


def _buyers_fixture() -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_PVD_SEGMENT: ["rich", "rich", "standard", "low", "low", "low"],
            COL_BUDGET_EFFECTIVE: [120.0, 110.0, 80.0, 40.0, 35.0, 30.0],
            COL_BUDGET_BASELINE: [100.0, 100.0, 80.0, 50.0, 50.0, 50.0],
            COL_FREQ_EFFECTIVE: [0.5, 0.4, 0.3, 0.1, 0.0, 0.2],
            COL_SCAR_FACTOR: [0.0, 0.1, 0.2, 0.3, 0.4, 0.5],
            COL_IS_CHURNED: [False, False, False, False, True, False],
        }
    )


def test_14_4_aggregate_segment_health_three_rows() -> None:
    rows = aggregate_segment_health(_buyers_fixture())
    assert [r["segment"] for r in rows] == ["rich", "standard", "low"]
    low = rows[2]
    assert low["n_buyers"] == 3
    assert low["n_active"] == 2
    assert low["churn_share"] == pytest.approx(1.0 / 3.0)


def test_14_4_t1_segments_endpoint_three_rows() -> None:
    memory = SegmentSnapshotMemory()
    memory.write(tick_id=3, rows=aggregate_segment_health(_buyers_fixture()))

    worker = MagicMock()
    worker.state = MagicMock(name="IDLE")
    app = create_app(worker=worker)
    app.state.segment_memory = memory
    client = TestClient(app)

    resp = client.get("/api/v1/analytics/segments?tick_id=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["tick_id"] == 3
    assert len(body["rows"]) == 3
    assert [r["segment"] for r in body["rows"]] == ["rich", "standard", "low"]


def test_14_4_t4_segments_endpoint_is_o1_read(monkeypatch: pytest.MonkeyPatch) -> None:
    memory = SegmentSnapshotMemory()
    memory.write(tick_id=1, rows=aggregate_segment_health(_buyers_fixture()))

    called = {"n": 0}

    def _boom(*_a, **_k):  # noqa: ANN001
        called["n"] += 1
        raise AssertionError("aggregate must not run inside GET")

    monkeypatch.setattr(
        "market_abm.api.routers.analytics.aggregate_segment_health",
        _boom,
    )

    worker = MagicMock()
    worker.state = MagicMock(name="IDLE")
    app = create_app(worker=worker)
    app.state.segment_memory = memory
    client = TestClient(app)

    resp = client.get("/api/v1/analytics/segments")
    assert resp.status_code == 200
    assert called["n"] == 0
    assert len(resp.json()["rows"]) == 3


def test_14_4_t2_strategy_pulse_three_strategies() -> None:
    products = pl.DataFrame(
        {
            COL_STRATEGY_TYPE: ["MaxProfit", "MaxProfit", "MaxVolume", "RatingMaximizer"],
            COL_DEMAND_INDEX: [1.0, 1.2, 0.8, 1.5],
        }
    )
    pulse = aggregate_strategy_pulse(products, panic_active=True, tick_id=2)
    assert pulse["panic_active"] is True
    names = [s["strategy_type"] for s in pulse["strategies"]]
    assert names == ["MaxProfit", "MaxVolume", "RatingMaximizer"]
    assert pulse["strategies"][0]["avg_demand_index"] == pytest.approx(1.1)

    memory = StrategyPulseMemory()
    memory.write(2, pulse)
    worker = MagicMock()
    worker.state = MagicMock(name="RUNNING")
    app = create_app(worker=worker)
    app.state.strategy_pulse_memory = memory
    client = TestClient(app)
    resp = client.get("/api/v1/analytics/strategy-pulse?tick_id=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["panic_active"] is True
    assert len(body["strategies"]) == 3


def test_14_4_t3_ranking_breakdown_weights_sum() -> None:
    products = pl.DataFrame(
        {
            COL_LISTING_ID: [10, 11],
            COL_SELLER_ID: [1, 2],
            COL_PRICE: [100.0, 120.0],
            COL_RATING_VALUE: [0.8, 0.5],
            "category_id": [0, 0],
        }
    )
    breakdown = compute_listing_ranking_breakdown(
        products,
        seller_id=1,
        ranking=RankingConfig(),
        sales_volume_by_listing={10: 5.0},
    )
    assert breakdown is not None
    assert breakdown["w1"] + breakdown["w2"] + breakdown["w3"] == pytest.approx(1.0)
    assert breakdown["score"] == pytest.approx(
        breakdown["term_rating"] + breakdown["term_price"] + breakdown["term_sales"]
    )

    worker = MagicMock()
    worker.state = MagicMock(name="IDLE")
    app = create_app(worker=worker)
    app.state.ranking_products = products
    client = TestClient(app)
    resp = client.get("/api/v1/analytics/listing-ranking?seller_id=1&tick_id=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["w1"] + body["w2"] + body["w3"] == pytest.approx(1.0)
