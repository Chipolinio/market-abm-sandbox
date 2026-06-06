# Назначение файла: конфиги много-тикового прогона симуляции (Slice 004).
# Базовая идея: SimulationRunConfig объединяет choice, repricing, bootstrap и persistence.
from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.events import SystemEventsConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.shocks import ShockCatalogConfig
from market_abm.config.simulation import ChoiceModelConfig


class ProductsBootstrapConfig(BaseModel):
    """Параметры сэмплирования полей карточки при listings → products."""

    model_config = {"frozen": True}

    delivery_days_min: float = Field(default=1.0, gt=0.0)
    delivery_days_max: float = Field(default=7.0, gt=0.0)
    rating_min: float = Field(default=3.0, ge=0.0, le=5.0)
    rating_max: float = Field(default=5.0, ge=0.0, le=5.0)

    @model_validator(mode="after")
    def _ranges(self) -> Self:
        if self.delivery_days_max < self.delivery_days_min:
            raise ValueError("delivery_days_max must be >= delivery_days_min")
        if self.rating_max < self.rating_min:
            raise ValueError("rating_max must be >= rating_min")
        return self


class PersistenceConfig(BaseModel):
    """Параметры записи прогона на диск (используется с 4.3)."""

    model_config = {"frozen": True}

    enabled: bool = True
    base_dir: str = "output"
    run_id: str | None = None
    duckdb_memory_limit: str = "2GB"


class SimulationRunConfig(BaseModel):
    """Параметры полного прогона run_simulation (без n_ticks — аргумент функции)."""

    model_config = {"frozen": True}

    seed: int | None = None
    choice: ChoiceModelConfig = Field(default_factory=ChoiceModelConfig)
    repricing: RepricingConfig = Field(default_factory=RepricingConfig.default_market)
    products_bootstrap: ProductsBootstrapConfig = Field(default_factory=ProductsBootstrapConfig)
    persistence: PersistenceConfig = Field(default_factory=PersistenceConfig)
    runtime_mode: Literal["legacy", "extended"] = "legacy"
    economics: SellerEconomicsConfig = Field(default_factory=SellerEconomicsConfig)
    events: SystemEventsConfig = Field(default_factory=SystemEventsConfig)
    shock_catalog: ShockCatalogConfig = Field(default_factory=ShockCatalogConfig)
