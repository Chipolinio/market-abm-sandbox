# Назначение файла: unit-тесты apply_environment_shocks (Slice 8.1).
# Базовая идея: векторные шоки среды — чистые трансформеры DataFrame без мутации входа.
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.shocks import ShockCatalogConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_UNIT_COST,
)
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.simulation.context import SimulationContext
from market_abm.simulation.shocks import apply_environment_shocks


def _buyers_df(budgets: list[float]) -> pl.DataFrame:
    n = len(budgets)
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: budgets,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
    )


def _products_df(prices: list[float]) -> pl.DataFrame:
    n = len(prices)
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [50.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )


def _ctx_with_shock(shock_type: ShockType) -> SimulationContext:
    return SimulationContext(
        tick_id=0,
        active_shocks=(
            ActiveShock(
                shock_type=shock_type,
                intensity=1.0,
                remaining_ticks=10,
                applied_at_tick=0,
            ),
        ),
        platform_fee_rate=0.15,
    )


def test_apply_environment_shocks_demand_crash_scales_budget() -> None:
    buyers = _buyers_df([1000.0, 2000.0, 3000.0])
    products = _products_df([100.0])
    catalog = ShockCatalogConfig()
    ctx = _ctx_with_shock(ShockType.DEMAND_CRASH)

    buyers_out, products_out = apply_environment_shocks(buyers, products, ctx, catalog)

    assert buyers_out.select(COL_BUDGET).to_series().mean() == 1400.0
    assert products_out[COL_PRICE].to_list() == products[COL_PRICE].to_list()
    assert buyers.equals(buyers)


def test_apply_environment_shocks_none_is_identity() -> None:
    buyers = _buyers_df([500.0, 600.0])
    products = _products_df([100.0, 200.0])
    catalog = ShockCatalogConfig()

    buyers_out, products_out = apply_environment_shocks(buyers, products, None, catalog)

    assert buyers_out.equals(buyers)
    assert products_out.equals(products)


def test_platform_fee_hike_increases_price() -> None:
    products = _products_df([100.0, 200.0])
    buyers = _buyers_df([500.0])
    catalog = ShockCatalogConfig()
    ctx = _ctx_with_shock(ShockType.PLATFORM_FEE_HIKE)

    _, products_out = apply_environment_shocks(buyers, products, ctx, catalog)

    assert products_out[COL_PRICE].min() > products[COL_PRICE].min()
    expected_multiplier = 1.0 + 0.15 + catalog.platform_fee_hike.fee_delta
    prices_out = products_out[COL_PRICE].to_list()
    assert prices_out[0] == pytest.approx(100.0 * expected_multiplier, rel=1e-4)
    assert prices_out[1] == pytest.approx(200.0 * expected_multiplier, rel=1e-4)


def test_marketplace_promotion_lowers_price_with_cap() -> None:
    products = _products_df([100.0, 200.0])
    buyers = _buyers_df([500.0])
    catalog = ShockCatalogConfig()
    ctx = _ctx_with_shock(ShockType.MARKETPLACE_PROMOTION)

    _, products_out = apply_environment_shocks(buyers, products, ctx, catalog)

    discount = catalog.marketplace_promotion.fee_delta
    assert products_out["price"].max() < products["price"].max()
    assert products_out["price"][0] == pytest.approx(100.0 * (1.0 - discount), rel=1e-4)
    assert "promotion_anchor_price" in products_out.columns
