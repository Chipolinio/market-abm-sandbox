# Purpose: Initialize listings_df from sellers_df for slice 002 market bootstrapping.
# Core idea: Build deterministic listing rows with price floor safety from seller margins.
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.repricing import ListingInitConfig
from market_abm.domain.constants import (
    COL_BASE_COMMISSION,
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_LOGISTIC_FEE,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_SELLER_ID,
    COL_UNIT_COST,
    LISTINGS_SCHEMA_DTYPES,
    PLATFORM_DEFAULTS,
    SELLERS_COLUMNS,
)
from market_abm.population.distributions import sample_from_spec


def listings_polars_schema() -> dict[str, pl.DataType]:
    """Map domain dtype names to Polars dtypes for listings_df."""
    return {name: getattr(pl, dtype_name) for name, dtype_name in LISTINGS_SCHEMA_DTYPES.items()}


def _as_float32(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=np.float32)


def _price_floor(
    unit_cost: np.ndarray,
    margin_floor: np.ndarray,
    *,
    min_listing_price: float = 0.0,
) -> np.ndarray:
    total_fees = (
        PLATFORM_DEFAULTS[COL_BASE_COMMISSION] + PLATFORM_DEFAULTS[COL_LOGISTIC_FEE]
    )
    denom = 1.0 - margin_floor - total_fees
    floor = (unit_cost / denom).astype(np.float32)
    if min_listing_price > 0.0:
        return np.maximum(floor, np.float32(min_listing_price))
    return floor


def _validate_sellers_df_contract(sellers_df: pl.DataFrame) -> None:
    missing = [col for col in SELLERS_COLUMNS if col not in sellers_df.columns]
    if missing:
        raise ValueError(f"sellers_df is missing required columns: {missing}")
    if sellers_df.height == 0:
        raise ValueError("sellers_df must be non-empty")


def _assign_category_ids(
    seller_ids: np.ndarray,
    n_categories: int,
    seed: int,
) -> np.ndarray:
    """
    Assign category_id to each listing via seeded modular hash (§16.4).
    Guarantees each category gets at least 1 listing when n_sellers ≥ n_categories.
    """
    rng = np.random.default_rng([seed, 0xC07012])  # salt for category assignment
    n = len(seller_ids)
    if n_categories <= 0:
        return np.zeros(n, dtype=np.int32)
    # Shuffle full cycle first to ensure coverage, then assign remainder uniformly
    base = np.tile(np.arange(n_categories, dtype=np.int32), (n // n_categories) + 1)[:n]
    rng.shuffle(base)
    return base


def initialize_listings(
    sellers_df: pl.DataFrame,
    config: ListingInitConfig,
    *,
    seed: int,
    min_listing_price: float = 0.0,
    n_categories: int = 5,
) -> pl.DataFrame:
    """Initialize listings_df with one listing per seller (listing_id == seller_id).

    Adds `category_id` column (Spec 012 §7.1) via seeded shuffle-cycle assignment.
    """
    _validate_sellers_df_contract(sellers_df)

    n = sellers_df.height
    rng = np.random.default_rng(seed)

    seller_id = sellers_df[COL_SELLER_ID].to_numpy().astype(np.int32, copy=False)
    margin_floor = sellers_df[COL_MARGIN_FLOOR].to_numpy().astype(np.float32, copy=False)

    unit_cost = _as_float32(sample_from_spec(config.unit_cost, n, rng))
    base_price = (unit_cost * (1.0 + config.initial_margin_markup)).astype(np.float32)
    floor = _price_floor(unit_cost, margin_floor, min_listing_price=min_listing_price)
    target_floor = (floor * config.minimum_price_to_floor_ratio).astype(np.float32)
    price = np.maximum(base_price, target_floor).astype(np.float32)
    demand_index = np.full(n, config.initial_demand_index, dtype=np.float32)
    category_id = _assign_category_ids(seller_id, n_categories, seed)

    schema = listings_polars_schema()
    return pl.DataFrame(
        {
            COL_LISTING_ID: seller_id,
            COL_SELLER_ID: seller_id,
            COL_UNIT_COST: unit_cost,
            COL_PRICE: price,
            COL_DEMAND_INDEX: demand_index,
        },
        schema=schema,
    ).with_columns(pl.Series(COL_CATEGORY_ID, category_id, dtype=pl.Int32))
