# Purpose: Validate listings_df initialization contract for slice 002.
# Core idea: Ensure deterministic, schema-safe, and economically valid initial prices.
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.repricing import ListingInitConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.domain.constants import (
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_SELLER_ID,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PLATFORM_DEFAULTS,
)
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings, listings_polars_schema


@pytest.fixture
def sellers_df() -> pl.DataFrame:
    return generate_sellers(SellerPopulationConfig.default_market(n_sellers=1_000, seed=11))


def test_initialize_listings_shape_and_schema(sellers_df: pl.DataFrame) -> None:
    listings = initialize_listings(sellers_df, ListingInitConfig.default_market(), seed=5)
    assert listings.height == sellers_df.height
    assert listings.columns == list(LISTINGS_COLUMNS)
    expected = listings_polars_schema()
    for col, dtype in expected.items():
        assert listings[col].dtype == dtype


def test_initialize_listings_listing_id_equals_seller_id(sellers_df: pl.DataFrame) -> None:
    listings = initialize_listings(sellers_df, ListingInitConfig.default_market(), seed=5)
    assert listings[COL_LISTING_ID].equals(listings[COL_SELLER_ID])


def test_initialize_listings_unit_cost_positive_and_price_above_floor(
    sellers_df: pl.DataFrame,
) -> None:
    listings = initialize_listings(sellers_df, ListingInitConfig.default_market(), seed=5)
    assert listings[COL_UNIT_COST].min() > 0.0

    joined = listings.join(
        sellers_df.select([COL_SELLER_ID, COL_MARGIN_FLOOR]),
        on=COL_SELLER_ID,
        how="left",
    )
    total_fees = (
        PLATFORM_DEFAULTS["base_commission"] + PLATFORM_DEFAULTS["logistic_fee"]
    )
    denom = 1.0 - joined[COL_MARGIN_FLOOR] - total_fees
    p_min = joined[COL_UNIT_COST] / denom
    assert (joined[COL_PRICE] >= p_min).all()


def test_initialize_listings_sets_constant_initial_demand(sellers_df: pl.DataFrame) -> None:
    listings = initialize_listings(
        sellers_df,
        ListingInitConfig.default_market(initial_demand_index=1.3),
        seed=5,
    )
    assert listings[COL_DEMAND_INDEX].min() == pytest.approx(1.3)
    assert listings[COL_DEMAND_INDEX].max() == pytest.approx(1.3)


def test_initialize_listings_is_deterministic_by_seed(sellers_df: pl.DataFrame) -> None:
    config = ListingInitConfig.default_market()
    a = initialize_listings(sellers_df, config, seed=77)
    b = initialize_listings(sellers_df, config, seed=77)
    c = initialize_listings(sellers_df, config, seed=78)
    assert a.equals(b)
    assert not a.equals(c)


def test_initialize_listings_requires_non_empty_sellers() -> None:
    empty = pl.DataFrame(
        {
            "seller_id": [],
            "strategy_type": [],
            "capital": [],
            "margin_floor": [],
            "repricing_speed": [],
        }
    )
    with pytest.raises(ValueError):
        initialize_listings(empty, ListingInitConfig.default_market(), seed=1)


def test_initialize_listings_requires_required_seller_columns(
    sellers_df: pl.DataFrame,
) -> None:
    bad = sellers_df.drop("margin_floor")
    with pytest.raises(ValueError):
        initialize_listings(bad, ListingInitConfig.default_market(), seed=1)
