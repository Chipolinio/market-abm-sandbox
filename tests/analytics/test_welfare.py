# Spec 015 slice 15.2 — welfare / HHI / price moments (pure Polars).
from __future__ import annotations

import math

import polars as pl
import pytest

from market_abm.analytics.welfare import (
    compute_tick_hhi,
    compute_tick_price_moments,
    compute_tick_welfare,
)
from market_abm.domain.constants import (
    COL_BUDGET_EFFECTIVE,
    COL_BUYER_ID,
    COL_LISTING_ID,
    COL_PRICE_PAID,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
)


def _tx(
    *,
    price_paid: list[float],
    unit_cost: list[float],
    buyer_id: list[int] | None = None,
    seller_id: list[int] | None = None,
) -> pl.DataFrame:
    n = len(price_paid)
    buyer_id = buyer_id if buyer_id is not None else list(range(n))
    seller_id = seller_id if seller_id is not None else list(range(n))
    return pl.DataFrame(
        {
            COL_TICK_ID: [0] * n,
            COL_BUYER_ID: buyer_id,
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: seller_id,
            COL_PRICE_PAID: price_paid,
            COL_UNIT_COST: unit_cost,
            "gross_margin": [p - c for p, c in zip(price_paid, unit_cost, strict=True)],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col("gross_margin").cast(pl.Float32),
    )


def _buyers(budget_by_id: dict[int, float]) -> pl.DataFrame:
    ids = sorted(budget_by_id)
    return pl.DataFrame(
        {
            COL_BUYER_ID: ids,
            COL_BUDGET_EFFECTIVE: [budget_by_id[i] for i in ids],
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET_EFFECTIVE).cast(pl.Float32),
    )


def test_15_2_t1_producer_surplus_price_minus_cost() -> None:
    """15.2-T1: 1 tx p=120, c=100 → PS=20."""
    tx = _tx(price_paid=[120.0], unit_cost=[100.0], buyer_id=[0], seller_id=[0])
    buyers = _buyers({0: 200.0})
    out = compute_tick_welfare(tx, buyers, platform_fee_rate=0.0)
    assert out["producer_surplus"] == pytest.approx(20.0)
    assert out["n_tx"] == 1


def test_15_2_t2_platform_profit_fee_rate() -> None:
    """15.2-T2: p=100, fee=0.1 → platform=10."""
    tx = _tx(price_paid=[100.0], unit_cost=[50.0], buyer_id=[0], seller_id=[0])
    buyers = _buyers({0: 200.0})
    out = compute_tick_welfare(tx, buyers, platform_fee_rate=0.1)
    assert out["platform_profit"] == pytest.approx(10.0)


def test_15_2_t3_consumer_surplus_proxy_budget_minus_price() -> None:
    """15.2-T3: budget=200, p=80 → CS_proxy=120."""
    tx = _tx(price_paid=[80.0], unit_cost=[20.0], buyer_id=[7], seller_id=[1])
    buyers = _buyers({7: 200.0})
    out = compute_tick_welfare(tx, buyers, platform_fee_rate=0.0)
    assert out["consumer_surplus_proxy"] == pytest.approx(120.0)


def test_15_2_t4_hhi_two_sellers_equal() -> None:
    """15.2-T4: equal revenue → HHI = 5000 (FTC 0–10000)."""
    tx = _tx(
        price_paid=[50.0, 50.0],
        unit_cost=[10.0, 10.0],
        buyer_id=[0, 1],
        seller_id=[1, 2],
    )
    hhi = compute_tick_hhi(tx)
    assert hhi == pytest.approx(5000.0)


def test_15_2_t5_empty_tx_welfare_zeros() -> None:
    """15.2-T5: n_tx=0 → CS/PS/platform=0; HHI=0.0 (not NaN)."""
    tx = _tx(price_paid=[], unit_cost=[])
    buyers = _buyers({0: 100.0})
    out = compute_tick_welfare(tx, buyers, platform_fee_rate=0.15)
    assert out["n_tx"] == 0
    assert out["consumer_surplus_proxy"] == 0.0
    assert out["producer_surplus"] == 0.0
    assert out["platform_profit"] == 0.0
    hhi = compute_tick_hhi(tx)
    assert hhi == 0.0
    assert not math.isnan(hhi)


def test_15_2_price_moments_prefer_tx_prices() -> None:
    """Price moments use price_paid when transactions non-empty."""
    tx = _tx(
        price_paid=[10.0, 30.0],
        unit_cost=[1.0, 1.0],
        buyer_id=[0, 1],
        seller_id=[0, 1],
    )
    moments = compute_tick_price_moments(tx)
    assert moments["median_price"] == pytest.approx(20.0)
    assert moments["price_std"] == pytest.approx(float(pl.Series([10.0, 30.0]).std()))
