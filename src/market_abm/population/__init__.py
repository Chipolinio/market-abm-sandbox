# Чистые функции генерации и трансформации DataFrame-населений (scipy → NumPy → Polars).
from market_abm.population.buyers import buyers_polars_schema, generate_buyers
from market_abm.population.distributions import (
    sample_activity_hours,
    sample_bernoulli,
    sample_categorical,
    sample_from_spec,
)

__all__ = [
    "buyers_polars_schema",
    "generate_buyers",
    "sample_activity_hours",
    "sample_bernoulli",
    "sample_categorical",
    "sample_from_spec",
]
