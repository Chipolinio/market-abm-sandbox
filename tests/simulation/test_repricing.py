# Purpose: Validate one-tick repricing behavior for slice 002 strategies.
# Core idea: Ensure strategy rules, activation mask, and price floor clipping are correct.
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import (
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.repricing import apply_repricing_tick, min_price_from_margin


def _sellers_df(
    seller_ids: list[int],
    strategy_types: list[str],
    margin_floors: list[float],
    speeds: list[int],
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: strategy_types,
            "capital": [100.0] * n,
            COL_MARGIN_FLOOR: margin_floors,
            COL_REPRICING_SPEED: speeds,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings_df(
    seller_ids: list[int],
    unit_costs: list[float],
    prices: list[float],
    demands: list[float],
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: seller_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: unit_costs,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: demands,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )


def test_max_profit_reacts_to_high_low_and_neutral_demand() -> None:
    sellers = _sellers_df([0, 1, 2], ["MaxProfit", "MaxProfit", "MaxProfit"], [0.2, 0.2, 0.2], [1, 1, 1])
    listings = _listings_df([0, 1, 2], [20.0, 20.0, 20.0], [100.0, 100.0, 100.0], [1.5, 0.5, 1.0])
    out = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    assert out[COL_PRICE].to_list() == pytest.approx([102.0, 98.0, 100.0])


def test_max_volume_drops_price_more_aggressively_than_max_profit() -> None:
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxVolume"], [0.2, 0.2], [1, 1])
    listings = _listings_df([0, 1], [20.0, 20.0], [100.0, 100.0], [0.5, 0.5])
    out = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    prices = out.sort(COL_SELLER_ID)[COL_PRICE].to_list()
    assert prices[0] == pytest.approx(98.0)
    assert prices[1] == pytest.approx(97.0)
    assert (100.0 - prices[1]) > (100.0 - prices[0])


def test_rating_maximizer_keeps_price_unchanged() -> None:
    sellers = _sellers_df([0], ["RatingMaximizer"], [0.2], [1])
    listings = _listings_df([0], [20.0], [100.0], [10.0])
    out = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    assert out[COL_PRICE].item() == pytest.approx(100.0)


def test_repricing_speed_controls_activation_mask() -> None:
    sellers = _sellers_df([0], ["MaxProfit"], [0.2], [3])
    listings = _listings_df([0], [20.0], [100.0], [1.5])
    out_tick_1 = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    out_tick_3 = apply_repricing_tick(sellers, listings, tick=3, config=RepricingConfig.default_market())
    assert out_tick_1[COL_PRICE].item() == pytest.approx(100.0)
    assert out_tick_3[COL_PRICE].item() == pytest.approx(102.0)


def test_price_is_clipped_to_price_floor() -> None:
    sellers = _sellers_df([0], ["MaxProfit"], [0.7], [1])
    listings = _listings_df([0], [20.0], [50.0], [0.1])
    out = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    assert out[COL_PRICE].item() == pytest.approx(200.0)


def test_inactive_rows_remain_identical_to_input() -> None:
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxProfit"], [0.2, 0.2], [2, 1])
    listings = _listings_df([0, 1], [20.0, 20.0], [100.0, 100.0], [1.5, 1.5])
    out = apply_repricing_tick(sellers, listings, tick=1, config=RepricingConfig.default_market())
    before = listings.filter(pl.col(COL_SELLER_ID) == 0)
    after = out.filter(pl.col(COL_SELLER_ID) == 0)
    assert before.equals(after)


def test_repricing_is_deterministic_for_same_inputs() -> None:
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxVolume"], [0.2, 0.2], [1, 1])
    listings = _listings_df([0, 1], [20.0, 20.0], [100.0, 100.0], [1.2, 0.8])
    cfg = RepricingConfig.default_market()
    a = apply_repricing_tick(sellers, listings, tick=5, config=cfg)
    b = apply_repricing_tick(sellers, listings, tick=5, config=cfg)
    assert a.equals(b)


def test_negative_tick_is_rejected() -> None:
    sellers = _sellers_df([0], ["MaxProfit"], [0.2], [1])
    listings = _listings_df([0], [20.0], [100.0], [1.2])
    with pytest.raises(ValueError):
        apply_repricing_tick(sellers, listings, tick=-1, config=RepricingConfig.default_market())


def test_min_price_expr_matches_manual_formula() -> None:
    df = pl.DataFrame({"unit_cost": [20.0], "margin_floor": [0.2]}).with_columns(
        pl.col("unit_cost").cast(pl.Float32),
        pl.col("margin_floor").cast(pl.Float32),
    )
    p_min = df.select(
        min_price_from_margin(pl.col("unit_cost"), pl.col("margin_floor")).alias("p_min")
    )["p_min"].item()
    assert p_min == pytest.approx(20.0 / (1.0 - 0.2 - 0.15 - 0.05))
