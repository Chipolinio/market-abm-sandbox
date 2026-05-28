# Чистые функции генерации и трансформации DataFrame-населений (scipy → NumPy → Polars).
from market_abm.population.buyers import buyers_polars_schema, generate_buyers
from market_abm.population.distributions import (
    sample_activity_hours,
    sample_bernoulli,
    sample_categorical,
    sample_from_spec,
)
from market_abm.population.sellers import generate_sellers, sellers_polars_schema

__all__ = [
    "buyers_polars_schema",
    "generate_buyers",
    "generate_sellers",
    "sample_activity_hours",
    "sample_bernoulli",
    "sample_categorical",
    "sample_from_spec",
    "sellers_polars_schema",
]
