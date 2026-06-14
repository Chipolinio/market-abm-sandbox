# Векторная сборка buyers_df из BuyerPopulationConfig (NumPy → Polars, без OOP-агентов).
"""generate_buyers — единственная точка входа; агент = строка таблицы."""

from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.domain.constants import (
    BUYERS_SCHEMA_DTYPES,
    COL_ACTIVITY_HOUR,
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUYER_ID,
    COL_DEVICE_TYPE,
    COL_IS_IMPULSIVE,
    COL_PURCHASE_FREQUENCY,
    COL_PVD_SEGMENT,
    PVD_BUDGET_MULTIPLIERS,
)
from market_abm.population.distributions import (
    sample_activity_hours,
    sample_bernoulli,
    sample_categorical,
    sample_from_spec,
)

_BETA_COLUMNS: tuple[str, ...] = (COL_BETA_PRICE, COL_BETA_DELIVERY, COL_BETA_RATING)


def buyers_polars_schema() -> dict[str, pl.DataType]:
    """Словарь Polars-dtype по доменному контракту BUYERS_SCHEMA_DTYPES."""
    return {name: getattr(pl, dtype_name) for name, dtype_name in BUYERS_SCHEMA_DTYPES.items()}


def _as_float32(arr: np.ndarray) -> np.ndarray:
    return np.asarray(arr, dtype=np.float32)


def _validate_negative_betas(
    arrays: dict[str, np.ndarray],
    *,
    enforce: bool,
) -> None:
    if not enforce:
        return
    for col in _BETA_COLUMNS:
        if np.any(arrays[col] >= 0):
            raise ValueError(
                f"{col}: при enforce_negative_coefficients=True все β должны быть < 0"
            )


def _apply_ios_beta_multiplier(
    beta_price: np.ndarray,
    device_type: np.ndarray,
    multiplier: float,
) -> np.ndarray:
    out = beta_price.copy()
    ios_mask = device_type == "ios"
    out[ios_mask] = (out[ios_mask] * multiplier).astype(np.float32)
    return out


def _apply_pvd_budget_multiplier(
    budget: np.ndarray,
    pvd_segment: np.ndarray,
) -> np.ndarray:
    lookup = np.vectorize(PVD_BUDGET_MULTIPLIERS.__getitem__, otypes=[np.float32])
    return (budget * lookup(pvd_segment)).astype(np.float32)


def generate_buyers(config: BuyerPopulationConfig) -> pl.DataFrame:
    """
    Собирает синтетическую популяцию покупателей как ``buyers_df``.

    Все агенты — строки одной таблицы; сэмплирование векторное, без Python-объектов на покупателя.
    """
    if config.activity_hour != "uniform_discrete":
        raise ValueError(f"Неподдерживаемый activity_hour: {config.activity_hour!r}")

    n = config.n_buyers
    rng = np.random.default_rng(config.seed)

    buyer_id = np.arange(
        config.buyer_id_start,
        config.buyer_id_start + n,
        dtype=np.int32,
    )
    budget = _as_float32(sample_from_spec(config.budget, n, rng))
    beta_price = _as_float32(sample_from_spec(config.beta_price, n, rng))
    beta_delivery = _as_float32(sample_from_spec(config.beta_delivery, n, rng))
    beta_rating = _as_float32(sample_from_spec(config.beta_rating, n, rng))

    device_type = sample_categorical(config.device_type, n, rng)
    pvd_segment = sample_categorical(config.pvd_segment, n, rng)
    activity_hour = sample_activity_hours(n, rng)
    is_impulsive = sample_bernoulli(config.impulsive_probability, n, rng)
    purchase_frequency = np.clip(
        sample_from_spec(config.purchase_frequency, n, rng),
        0.0,
        1.0,
    ).astype(np.float32)

    arrays = {
        COL_BETA_PRICE: beta_price,
        COL_BETA_DELIVERY: beta_delivery,
        COL_BETA_RATING: beta_rating,
    }
    _validate_negative_betas(arrays, enforce=config.enforce_negative_coefficients)

    beta_price = _apply_ios_beta_multiplier(
        arrays[COL_BETA_PRICE],
        device_type,
        config.ios_price_beta_multiplier,
    )
    budget = _apply_pvd_budget_multiplier(budget, pvd_segment)
    budget_baseline = budget.copy()

    schema = buyers_polars_schema()
    return pl.DataFrame(
        {
            COL_BUYER_ID: buyer_id,
            COL_BUDGET: budget,
            COL_BUDGET_BASELINE: budget_baseline,
            COL_BETA_PRICE: beta_price,
            COL_BETA_DELIVERY: arrays[COL_BETA_DELIVERY],
            COL_BETA_RATING: arrays[COL_BETA_RATING],
            COL_DEVICE_TYPE: pl.Series(COL_DEVICE_TYPE, device_type).cast(
                pl.Categorical
            ),
            COL_PVD_SEGMENT: pl.Series(COL_PVD_SEGMENT, pvd_segment).cast(
                pl.Categorical
            ),
            COL_ACTIVITY_HOUR: activity_hour,
            COL_IS_IMPULSIVE: is_impulsive,
            COL_PURCHASE_FREQUENCY: purchase_frequency,
        },
        schema=schema,
    )
