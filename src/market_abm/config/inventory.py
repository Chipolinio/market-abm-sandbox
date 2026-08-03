# Spec 012.1 §8 — inventory / stockout / replenishment configuration.
from __future__ import annotations

from pydantic import BaseModel, Field


class InventoryConfig(BaseModel):
    """
    Stock ledger + OOS hider (Spec 012.1 §4).

    enabled=False → legacy infinite stock (Spec 008 settle unchanged).
    """

    model_config = {"frozen": True}

    enabled: bool = False
    stock_init_min: int = Field(default=20, ge=0)
    stock_init_max: int = Field(default=80, ge=0)
    default_stock_target: int | None = Field(
        default=None,
        ge=1,
        description="If set, stock_target column; else stock_target := stock_units at bootstrap",
    )


class InventoryPricingConfig(BaseModel):
    """Inventory pressure → rule repricing (Spec 012.1 §5). Slice 12.1.2."""

    model_config = {"frozen": True}

    enabled: bool = False
    pressure_alpha: float = Field(default=0.5, ge=0.0)
    pressure_beta: float = Field(default=0.3, ge=0.0)
    inventory_step_gain: float = Field(default=1.0, ge=0.0)


class ReplenishmentConfig(BaseModel):
    """Reorder + lead time + prepaid COGS (Spec 012.1 §6). Slice 12.1.3."""

    model_config = {"frozen": True}

    enabled: bool = False
    reorder_point: int = Field(default=10, ge=0)
    reorder_quantity: int = Field(default=40, ge=1)
    lead_time_ticks: int = Field(default=5, ge=1)
    holding_cost_per_unit_tick: float = Field(default=0.05, ge=0.0)
