# Purpose: Validate vectorized sellers_df generation for slice 002.
# Core idea: Enforce domain schema, invariants, and deterministic sampling.
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.sellers import SellerPopulationConfig
from market_abm.domain.constants import (
    COL_CAPITAL,
    COL_MARGIN_FLOOR,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    MARGIN_FLOOR_DEFAULT_MAX,
    MARGIN_FLOOR_MIN,
    PLATFORM_DEFAULTS,
    REPRICING_SPEED_MAX,
    REPRICING_SPEED_MIN,
    SELLERS_COLUMNS,
    STRATEGY_TYPES,
)
from market_abm.population.sellers import generate_sellers, sellers_polars_schema


@pytest.fixture
def small_config() -> SellerPopulationConfig:
    return SellerPopulationConfig.default_market(n_sellers=1_000, seed=42)


def test_generate_sellers_shape_and_schema(small_config: SellerPopulationConfig) -> None:
    df = generate_sellers(small_config)
    assert df.height == small_config.n_sellers
    assert df.columns == list(SELLERS_COLUMNS)
    expected = sellers_polars_schema()
    for col, dtype in expected.items():
        actual = df[col].dtype
        if dtype == pl.Categorical:
            assert isinstance(actual, pl.Categorical)
        else:
            assert actual == dtype


def test_generate_sellers_deterministic_with_seed(small_config: SellerPopulationConfig) -> None:
    a = generate_sellers(small_config)
    b = generate_sellers(small_config)
    assert a.equals(b)


def test_generate_sellers_seller_id_sequential(small_config: SellerPopulationConfig) -> None:
    df = generate_sellers(small_config)
    expected = pl.Series(
        COL_SELLER_ID,
        np.arange(
            small_config.seller_id_start,
            small_config.seller_id_start + small_config.n_sellers,
            dtype=np.int32,
        ),
    )
    assert df[COL_SELLER_ID].equals(expected)


def test_generate_sellers_capital_and_margin_bounds(
    small_config: SellerPopulationConfig,
) -> None:
    df = generate_sellers(small_config)
    assert df[COL_CAPITAL].min() > 0.0
    assert df[COL_MARGIN_FLOOR].min() >= MARGIN_FLOOR_MIN
    assert df[COL_MARGIN_FLOOR].max() <= MARGIN_FLOOR_DEFAULT_MAX

    total_fees = (
        PLATFORM_DEFAULTS["base_commission"] + PLATFORM_DEFAULTS["logistic_fee"]
    )
    assert df[COL_MARGIN_FLOOR].max() < (1.0 - total_fees)


def test_generate_sellers_repricing_speed_is_clipped_to_uint8_bounds(
    small_config: SellerPopulationConfig,
) -> None:
    df = generate_sellers(small_config)
    assert df[COL_REPRICING_SPEED].min() >= REPRICING_SPEED_MIN
    assert df[COL_REPRICING_SPEED].max() <= REPRICING_SPEED_MAX


def test_generate_sellers_strategy_levels_subset_of_domain(
    small_config: SellerPopulationConfig,
) -> None:
    df = generate_sellers(small_config)
    assert set(df[COL_STRATEGY_TYPE].unique().to_list()).issubset(set(STRATEGY_TYPES))


def test_generate_sellers_default_strategy_mix_is_reasonable() -> None:
    config = SellerPopulationConfig.default_market(n_sellers=30_000, seed=7)
    df = generate_sellers(config)

    freq = (
        df.group_by(COL_STRATEGY_TYPE)
        .len()
        .with_columns((pl.col("len") / config.n_sellers).alias("share"))
    )
    shares = {row[COL_STRATEGY_TYPE]: row["share"] for row in freq.to_dicts()}

    assert shares["MaxProfit"] == pytest.approx(0.45, abs=0.03)
    assert shares["MaxVolume"] == pytest.approx(0.40, abs=0.03)
    assert shares["RatingMaximizer"] == pytest.approx(0.15, abs=0.03)
