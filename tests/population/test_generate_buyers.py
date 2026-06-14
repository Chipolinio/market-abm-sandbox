# Тесты generate_buyers: buyers_df, схема, инварианты, детерминизм (spec 001 §9.3, 010 §10.1).

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.buyers import BuyerPopulationConfig, DistributionSpec
from market_abm.domain.constants import (
    BUYERS_COLUMNS,
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_BUYER_ID,
    COL_DEVICE_TYPE,
    COL_FREQ_BASELINE,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_PURCHASE_FREQUENCY,
    COL_SCAR_FACTOR,
    DEVICE_TYPES,
    PVD_SEGMENTS,
)
from market_abm.population.buyers import buyers_polars_schema, generate_buyers


@pytest.fixture
def small_config() -> BuyerPopulationConfig:
    return BuyerPopulationConfig.default_market(n_buyers=500, seed=42)


def test_generate_buyers_shape_and_schema(small_config: BuyerPopulationConfig) -> None:
    df = generate_buyers(small_config)
    assert df.height == small_config.n_buyers
    assert df.columns == list(BUYERS_COLUMNS)
    expected = buyers_polars_schema()
    for col, dtype in expected.items():
        actual = df[col].dtype
        if dtype == pl.Categorical:
            assert isinstance(actual, pl.Categorical)
        else:
            assert actual == dtype


def test_generate_buyers_deterministic_with_seed(small_config: BuyerPopulationConfig) -> None:
    a = generate_buyers(small_config)
    b = generate_buyers(small_config)
    assert a.equals(b)


def test_generate_buyers_buyer_id_sequential(small_config: BuyerPopulationConfig) -> None:
    df = generate_buyers(small_config)
    expected = pl.Series(
        COL_BUYER_ID,
        np.arange(
            small_config.buyer_id_start,
            small_config.buyer_id_start + small_config.n_buyers,
            dtype=np.int32,
        ),
    )
    assert df[COL_BUYER_ID].equals(expected)


def test_generate_buyers_budget_strictly_positive(small_config: BuyerPopulationConfig) -> None:
    df = generate_buyers(small_config)
    assert df[COL_BUDGET].min() > 0


def test_generate_buyers_purchase_frequency_in_unit_interval(
    small_config: BuyerPopulationConfig,
) -> None:
    df = generate_buyers(small_config)
    col = df[COL_PURCHASE_FREQUENCY]
    assert col.min() >= 0.0
    assert col.max() <= 1.0


def test_generate_buyers_betas_negative_by_default(small_config: BuyerPopulationConfig) -> None:
    df = generate_buyers(small_config)
    assert df[COL_BETA_PRICE].max() < 0
    assert df[COL_BETA_DELIVERY].max() < 0
    assert df[COL_BETA_RATING].max() < 0


def test_generate_buyers_allows_positive_betas_when_enforcement_off() -> None:
    config = BuyerPopulationConfig.default_market(n_buyers=200, seed=1).model_copy(
        update={
            "enforce_negative_coefficients": False,
            "beta_price": DistributionSpec(
                family="norm", params={"loc": 1.0, "scale": 0.01}
            ),
        }
    )
    df = generate_buyers(config)
    assert df[COL_BETA_PRICE].min() > 0


def test_generate_buyers_ios_lower_abs_beta_price_than_android() -> None:
    config = BuyerPopulationConfig.default_market(n_buyers=20_000, seed=99)
    df = generate_buyers(config)
    ios_mean = df.filter(pl.col(COL_DEVICE_TYPE) == "ios")[COL_BETA_PRICE].abs().mean()
    android_mean = df.filter(pl.col(COL_DEVICE_TYPE) == "android")[COL_BETA_PRICE].abs().mean()
    assert ios_mean < android_mean


def test_generate_buyers_categorical_levels_subset_of_domain(
    small_config: BuyerPopulationConfig,
) -> None:
    df = generate_buyers(small_config)
    assert set(df[COL_DEVICE_TYPE].unique().to_list()).issubset(set(DEVICE_TYPES))
    assert set(df["pvd_segment"].unique().to_list()).issubset(set(PVD_SEGMENTS))


def test_generate_buyers_activity_hour_in_range(small_config: BuyerPopulationConfig) -> None:
    df = generate_buyers(small_config)
    assert df["activity_hour"].min() >= 0
    assert df["activity_hour"].max() <= 23


def test_default_market_smoke() -> None:
    df = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=100, seed=0))
    assert df.height == 100


# --- Spec 010 §10.1-T* ---


def test_generate_buyers_sets_budget_baseline_equal_budget(
    small_config: BuyerPopulationConfig,
) -> None:
    df = generate_buyers(small_config)
    assert df[COL_BUDGET].equals(df[COL_BUDGET_BASELINE])


def test_generate_buyers_budget_baseline_strictly_positive(
    small_config: BuyerPopulationConfig,
) -> None:
    df = generate_buyers(small_config)
    assert df[COL_BUDGET_BASELINE].min() > 0


def test_generate_buyers_economic_columns_initialized(
    small_config: BuyerPopulationConfig,
) -> None:
    df = generate_buyers(small_config)
    assert df[COL_FREQ_BASELINE].equals(df[COL_PURCHASE_FREQUENCY])
    assert df[COL_BUDGET_EFFECTIVE].equals(df[COL_BUDGET_BASELINE])
    assert df[COL_FREQ_EFFECTIVE].equals(df[COL_FREQ_BASELINE])
    assert df[COL_SCAR_FACTOR].max() == pytest.approx(0.0)
    assert not df[COL_IS_CHURNED].any()
