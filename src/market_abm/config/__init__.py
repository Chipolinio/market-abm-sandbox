# Слой Pydantic-конфигов симуляции (единственное место для BaseModel).
from market_abm.config.buyers import (
    BuyerPopulationConfig,
    CategoricalSpec,
    DistributionSpec,
)

__all__ = [
    "BuyerPopulationConfig",
    "CategoricalSpec",
    "DistributionSpec",
]
