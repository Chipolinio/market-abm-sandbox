from __future__ import annotations

import polars as pl
import pytest

from market_abm.domain import constants as c


def test_buyers_schema_has_ten_columns() -> None:
    assert len(c.BUYERS_COLUMNS) == 10
    assert len(c.BUYERS_SCHEMA_DTYPES) == 10


def test_buyers_columns_match_schema_keys() -> None:
    assert set(c.BUYERS_COLUMNS) == set(c.BUYERS_SCHEMA_DTYPES.keys())


def test_buyers_required_column_names() -> None:
    expected = {
        "buyer_id",
        "budget",
        "beta_price",
        "beta_delivery",
        "beta_rating",
        "device_type",
        "pvd_segment",
        "activity_hour",
        "is_impulsive",
        "purchase_frequency",
    }
    assert set(c.BUYERS_COLUMNS) == expected


def test_buyers_schema_dtypes_are_valid_polars_names() -> None:
    """Каждое имя dtype из домена должно резолвиться в pl.* для сборки DataFrame."""
    for col, dtype_name in c.BUYERS_SCHEMA_DTYPES.items():
        assert hasattr(pl, dtype_name), f"{col}: unknown Polars dtype {dtype_name!r}"


def test_device_types_and_pvd_segments_non_empty() -> None:
    assert len(c.DEVICE_TYPES) >= 2
    assert len(c.PVD_SEGMENTS) >= 2
    assert "ios" in c.DEVICE_TYPES
    assert "rich" in c.PVD_SEGMENTS


def test_pvd_budget_multipliers_cover_all_segments() -> None:
    for seg in c.PVD_SEGMENTS:
        assert seg in c.PVD_BUDGET_MULTIPLIERS
        assert c.PVD_BUDGET_MULTIPLIERS[seg] > 0


def test_sellers_schema_contract() -> None:
    assert len(c.SELLERS_COLUMNS) == 5
    assert set(c.SELLERS_SCHEMA_DTYPES.keys()) == set(c.SELLERS_COLUMNS)
    assert set(c.STRATEGY_TYPES) == {"MaxProfit", "MaxVolume", "RatingMaximizer"}


def test_listings_column_constants_exist_and_match_names() -> None:
    assert c.COL_LISTING_ID == "listing_id"
    assert c.COL_UNIT_COST == "unit_cost"
    assert c.COL_PRICE == "price"
    assert c.COL_DEMAND_INDEX == "demand_index"


def test_listings_columns_contract_order_is_stable() -> None:
    assert c.LISTINGS_COLUMNS == (
        c.COL_LISTING_ID,
        c.COL_SELLER_ID,
        c.COL_UNIT_COST,
        c.COL_PRICE,
        c.COL_DEMAND_INDEX,
    )


def test_listings_schema_dtypes_match_columns_one_to_one() -> None:
    assert tuple(c.LISTINGS_SCHEMA_DTYPES.keys()) == c.LISTINGS_COLUMNS
    assert c.LISTINGS_SCHEMA_DTYPES == {
        c.COL_LISTING_ID: "Int32",
        c.COL_SELLER_ID: "Int32",
        c.COL_UNIT_COST: "Float32",
        c.COL_PRICE: "Float32",
        c.COL_DEMAND_INDEX: "Float32",
    }


def test_products_columns_extend_listings_for_slice_003() -> None:
    assert c.PRODUCTS_COLUMNS[: len(c.LISTINGS_COLUMNS)] == c.LISTINGS_COLUMNS
    assert c.PRODUCTS_COLUMNS[-2:] == (c.COL_DELIVERY_DAYS, c.COL_RATING_VALUE)
    assert set(c.PRODUCTS_SCHEMA_DTYPES.keys()) == set(c.PRODUCTS_COLUMNS)


def test_choices_output_columns_contract() -> None:
    assert c.CHOICES_COLUMNS == (
        c.COL_BUYER_ID,
        c.COL_LISTING_ID,
        c.COL_CHOICE_PROBABILITY,
    )


def test_platform_defaults() -> None:
    assert set(c.PLATFORM_DEFAULTS.keys()) == set(c.PLATFORM_KEYS)
    assert all(0.0 < v < 1.0 for v in c.PLATFORM_DEFAULTS.values())


def test_market_guardrails_are_economically_consistent() -> None:
    assert c.MARGIN_FLOOR_MIN > 0.0
    assert c.MARGIN_FLOOR_DEFAULT_MAX <= c.MARGIN_FLOOR_HARD_MAX
    assert c.MARGIN_FLOOR_HARD_MAX < 1.0
    total_fees = (
        c.PLATFORM_DEFAULTS[c.COL_BASE_COMMISSION]
        + c.PLATFORM_DEFAULTS[c.COL_LOGISTIC_FEE]
    )
    assert c.MARGIN_FLOOR_HARD_MAX < (1.0 - total_fees)


def test_repricing_speed_and_demand_defaults_are_safe() -> None:
    assert c.REPRICING_SPEED_MIN == 1
    assert c.REPRICING_SPEED_MAX == 255
    assert c.DEFAULT_DEMAND_INDEX == 1.0
    assert c.MAX_PROFIT_DEMAND_HIGH_DEFAULT > c.DEFAULT_DEMAND_INDEX
    assert 0.0 < c.MAX_PROFIT_DEMAND_LOW_DEFAULT < c.DEFAULT_DEMAND_INDEX


@pytest.mark.parametrize(
    "col,dtype_name",
    list(c.BUYERS_SCHEMA_DTYPES.items()),
)
def test_buyers_polars_schema_build(col: str, dtype_name: str) -> None:
    """Сборка схемы Polars из доменных строк — контракт для generate_buyers."""
    dtype = getattr(pl, dtype_name)
    assert pl.Series(col, [], dtype=dtype).dtype == dtype
