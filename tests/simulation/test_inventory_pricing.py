# Spec 012.1, Slice 12.1.2: inventory pressure → rule pricing.
# RED before: no inventory term in apply_repricing_tick.
# GREEN after: excess → price↓; scarce → price↑; unit_cost floor; disabled noop.

from __future__ import annotations

import polars as pl

from market_abm.config.inventory import InventoryPricingConfig
from market_abm.config.repricing import CompetitorTrackingConfig, RepricingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.inventory import COL_INVENTORY_PRESSURE, compute_inventory_pressure
from market_abm.simulation.repricing import apply_repricing_tick

_TICK = 10  # past default warmup


def _sellers(n: int = 2, *, strategy: str = "MaxProfit") -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: [strategy] * n,
            "capital": [10_000.0] * n,
            COL_MARGIN_FLOOR: [0.0] * n,  # floor = unit_cost path via fees; use low floor
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings(
    *,
    prices: list[float],
    stocks: list[int],
    targets: list[int],
    unit_costs: list[float] | None = None,
    demand_index: float = 1.0,
) -> pl.DataFrame:
    n = len(prices)
    costs = unit_costs if unit_costs is not None else [20.0] * n
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: costs,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [demand_index] * n,
            COL_CATEGORY_ID: [0] * n,
            COL_STOCK_UNITS: stocks,
            COL_STOCK_TARGET: targets,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col(COL_STOCK_UNITS).cast(pl.Int32),
        pl.col(COL_STOCK_TARGET).cast(pl.Int32),
    )


def _reprice_cfg() -> RepricingConfig:
    return RepricingConfig(
        relative_step=0.05,
        min_listing_price=0.0,
        warmup_ticks=0,
        competitor=CompetitorTrackingConfig(enabled=False),
    )


def _pricing_cfg(**kw: object) -> InventoryPricingConfig:
    defaults: dict[str, object] = {
        "enabled": True,
        "pressure_alpha": 1.0,
        "pressure_beta": 0.0,
        "inventory_step_gain": 2.0,
    }
    defaults.update(kw)
    return InventoryPricingConfig(**defaults)


# ---------------------------------------------------------------------------
# Unit: compute_inventory_pressure
# ---------------------------------------------------------------------------


def test_pressure_positive_on_excess_stock() -> None:
    listings = _listings(prices=[100.0], stocks=[100], targets=[50])
    press = compute_inventory_pressure(listings, _pricing_cfg())
    assert press[COL_INVENTORY_PRESSURE][0] > 0.0


def test_pressure_negative_on_scarce_stock() -> None:
    listings = _listings(prices=[100.0], stocks=[10], targets=[50])
    press = compute_inventory_pressure(listings, _pricing_cfg())
    assert press[COL_INVENTORY_PRESSURE][0] < 0.0


# ---------------------------------------------------------------------------
# 12.1.2-T1  excess_stock_lowers_price
# ---------------------------------------------------------------------------


def test_excess_stock_lowers_price() -> None:
    """High cover_ratio → price decreases vs balanced peer (ceteris paribus)."""
    listings = _listings(
        prices=[100.0, 100.0],
        stocks=[100, 50],
        targets=[50, 50],
        demand_index=1.0,  # MaxProfit dead zone — no demand move
    )
    sellers = _sellers(2)
    out = apply_repricing_tick(
        sellers,
        listings,
        tick=_TICK,
        config=_reprice_cfg(),
        inventory_pricing=_pricing_cfg(),
    )
    prices = dict(
        zip(out[COL_LISTING_ID].to_list(), out[COL_PRICE].to_list(), strict=True)
    )
    assert prices[0] < prices[1], (
        f"excess listing must reprice lower: excess={prices[0]} balanced={prices[1]}"
    )
    assert prices[0] < 100.0


# ---------------------------------------------------------------------------
# 12.1.2-T2  scarce_stock_raises_price
# ---------------------------------------------------------------------------


def test_scarce_stock_raises_price() -> None:
    listings = _listings(
        prices=[100.0, 100.0],
        stocks=[10, 50],
        targets=[50, 50],
        demand_index=1.0,
    )
    sellers = _sellers(2)
    out = apply_repricing_tick(
        sellers,
        listings,
        tick=_TICK,
        config=_reprice_cfg(),
        inventory_pricing=_pricing_cfg(),
    )
    prices = dict(
        zip(out[COL_LISTING_ID].to_list(), out[COL_PRICE].to_list(), strict=True)
    )
    assert prices[0] > prices[1], (
        f"scarce listing must reprice higher: scarce={prices[0]} balanced={prices[1]}"
    )
    assert prices[0] > 100.0


# ---------------------------------------------------------------------------
# 12.1.2-T3  inventory_price_respects_unit_cost
# ---------------------------------------------------------------------------


def test_inventory_price_respects_unit_cost() -> None:
    """Scarce pressure cannot push price below unit_cost when forbid guard on."""
    listings = _listings(
        prices=[25.0],
        stocks=[1],
        targets=[100],
        unit_costs=[24.0],
        demand_index=1.0,
    )
    sellers = _sellers(1)
    # Large gain would try to raise, but we also test excess dumping into floor:
    listings_dump = _listings(
        prices=[25.0],
        stocks=[500],
        targets=[10],
        unit_costs=[24.0],
        demand_index=1.0,
    )
    cfg = _reprice_cfg()
    # Enable unit_cost floor via stress profile path: use forbid on config.stress
    from market_abm.simulation.repricing import RepricingProfile

    profile = RepricingProfile(
        stress=0.5,
        relative_step=cfg.relative_step,
        max_profit_demand_high=cfg.max_profit_demand_high,
        max_profit_demand_low=cfg.max_profit_demand_low,
        max_volume_aggression=cfg.max_volume_aggression,
        panic_margin_above_unit_cost=0.0,
        forbid_price_below_unit_cost=True,
        panic_mode=False,
    )
    out = apply_repricing_tick(
        sellers,
        listings_dump,
        tick=_TICK,
        config=cfg,
        repricing_profile=profile,
        inventory_pricing=_pricing_cfg(inventory_step_gain=50.0),
    )
    assert float(out[COL_PRICE][0]) >= 24.0 - 1e-4


# ---------------------------------------------------------------------------
# 12.1.2-T4  pricing_disabled_noop
# ---------------------------------------------------------------------------


def test_pricing_disabled_noop() -> None:
    listings = _listings(
        prices=[100.0, 100.0],
        stocks=[200, 10],
        targets=[50, 50],
        demand_index=1.0,
    )
    sellers = _sellers(2)
    disabled = InventoryPricingConfig(enabled=False)
    out = apply_repricing_tick(
        sellers,
        listings,
        tick=_TICK,
        config=_reprice_cfg(),
        inventory_pricing=disabled,
    )
    assert out[COL_PRICE].to_list() == [100.0, 100.0]
