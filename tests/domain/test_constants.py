# Тесты доменных констант: схемы buyers/sellers, категории, платформа (spec 001 §9.1).

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


def test_platform_defaults() -> None:
    assert set(c.PLATFORM_DEFAULTS.keys()) == set(c.PLATFORM_KEYS)
    assert all(0.0 < v < 1.0 for v in c.PLATFORM_DEFAULTS.values())


@pytest.mark.parametrize(
    "col,dtype_name",
    list(c.BUYERS_SCHEMA_DTYPES.items()),
)
def test_buyers_polars_schema_build(col: str, dtype_name: str) -> None:
    """Сборка схемы Polars из доменных строк — контракт для generate_buyers."""
    dtype = getattr(pl, dtype_name)
    assert pl.Series(col, [], dtype=dtype).dtype == dtype
