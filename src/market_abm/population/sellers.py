# Purpose: Build sellers_df from validated SellerPopulationConfig using vectorized sampling.
# Core idea: Keep seller generation pure, deterministic, and schema-driven.
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.sellers import SellerPopulationConfig
from market_abm.domain.constants import (
    COL_BASE_COMMISSION,
    COL_CAPITAL,
    COL_LOGISTIC_FEE,
    COL_MARGIN_FLOOR,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    MARGIN_FLOOR_DEFAULT_MAX,
    MARGIN_FLOOR_MIN,
    PLATFORM_DEFAULTS,
    REPRICING_SPEED_MAX,
    REPRICING_SPEED_MIN,
    SELLERS_SCHEMA_DTYPES,
)
from market_abm.population.distributions import sample_categorical, sample_from_spec


def sellers_polars_schema() -> dict[str, pl.DataType]:
    """Map domain dtype names to Polars dtypes for sellers_df."""
    return {name: getattr(pl, dtype_name) for name, dtype_name in SELLERS_SCHEMA_DTYPES.items()}


def _as_float32(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=np.float32)


def _margin_floor_upper_bound() -> float:
    total_fees = (
        PLATFORM_DEFAULTS[COL_BASE_COMMISSION] + PLATFORM_DEFAULTS[COL_LOGISTIC_FEE]
    )
    # Keep a tiny epsilon to preserve strict < 1 - fees invariant.
    return min(MARGIN_FLOOR_DEFAULT_MAX, (1.0 - total_fees) - 1e-6)


def generate_sellers(config: SellerPopulationConfig) -> pl.DataFrame:
    """Generate sellers_df with deterministic vectorized NumPy sampling."""
    n = config.n_sellers
    rng = np.random.default_rng(config.seed)

    seller_id = np.arange(
        config.seller_id_start,
        config.seller_id_start + n,
        dtype=np.int32,
    )
    strategy_type = sample_categorical(config.strategy_type, n, rng)
    capital = _as_float32(sample_from_spec(config.capital, n, rng))
    margin_floor_raw = _as_float32(sample_from_spec(config.margin_floor, n, rng))
    speed_raw = sample_from_spec(config.repricing_speed, n, rng)

    margin_floor = np.clip(
        margin_floor_raw,
        MARGIN_FLOOR_MIN,
        _margin_floor_upper_bound(),
    ).astype(np.float32)
    repricing_speed = np.clip(
        np.rint(speed_raw),
        REPRICING_SPEED_MIN,
        REPRICING_SPEED_MAX,
    ).astype(np.uint8)

    schema = sellers_polars_schema()
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_id,
            COL_STRATEGY_TYPE: pl.Series(COL_STRATEGY_TYPE, strategy_type).cast(
                pl.Categorical
            ),
            COL_CAPITAL: capital,
            COL_MARGIN_FLOOR: margin_floor,
            COL_REPRICING_SPEED: repricing_speed,
        },
        schema=schema,
    )
