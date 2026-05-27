# Пакет эконометрического ABM-симулятора маркетплейса (DOD: агенты = строки DataFrame).
"""Публичный API: домен, конфиг покупателей, generate_buyers."""

from market_abm.config.buyers import BuyerPopulationConfig, CategoricalSpec, DistributionSpec
from market_abm.domain.constants import (
    BUYERS_COLUMNS,
    BUYERS_SCHEMA_DTYPES,
    PLATFORM_DEFAULTS,
    SELLERS_COLUMNS,
    SELLERS_SCHEMA_DTYPES,
)
from market_abm.population.buyers import buyers_polars_schema, generate_buyers

__all__ = [
    "BUYERS_COLUMNS",
    "BUYERS_SCHEMA_DTYPES",
    "BuyerPopulationConfig",
    "CategoricalSpec",
    "DistributionSpec",
    "PLATFORM_DEFAULTS",
    "SELLERS_COLUMNS",
    "SELLERS_SCHEMA_DTYPES",
    "buyers_polars_schema",
    "generate_buyers",
]
