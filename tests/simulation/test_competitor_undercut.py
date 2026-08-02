# Spec 012, Slice 12.4: per-category competitor undercut signal in rule repricing.
# RED before: CompetitorTrackingConfig not in config/repricing.py;
#             compute_competitor_prices not in simulation/repricing.py.
# GREEN after: vectorized competitor_prices + undercut gate in apply_repricing_tick.

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.repricing import CompetitorTrackingConfig, RepricingConfig
from market_abm.domain.constants import (
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.repricing import apply_repricing_tick, compute_competitor_prices

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TOTAL_FEES = 0.20  # BASE_COMMISSION + LOGISTIC_FEE defaults


def _sellers(
    n: int,
    *,
    strategy: str = "MaxVolume",
    margin_floor: float = 0.0,
    repricing_speed: int = 1,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: [strategy] * n,
            "capital": [10_000.0] * n,
            COL_MARGIN_FLOOR: [margin_floor] * n,
            COL_REPRICING_SPEED: [repricing_speed] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings(
    prices: list[float],
    unit_costs: list[float],
    category_ids: list[int],
    *,
    demand_index: float = 1.0,
    margin_floor: float = 0.0,
) -> pl.DataFrame:
    n = len(prices)
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: unit_costs,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [demand_index] * n,
            COL_CATEGORY_ID: category_ids,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
    )


def _default_cfg(*, undercut_threshold: float = 0.05) -> RepricingConfig:
    return RepricingConfig(
        relative_step=0.02,
        min_listing_price=0.0,
        competitor=CompetitorTrackingConfig(
            enabled=True,
            undercut_threshold=undercut_threshold,
        ),
    )


# ---------------------------------------------------------------------------
# 12.4-T3  compute_competitor_prices — unit test for per-category min
# ---------------------------------------------------------------------------


def test_compute_competitor_prices_returns_per_category_minimum() -> None:
    """
    compute_competitor_prices adds min_competitor_price = cat_min.
    Listing at cat_min sees Δ_comp = 0 (no self-undercut).
    Sole listing in category sees cat_min = its own price (no undercut).
    """
    df = pl.DataFrame(
        {
            "listing_id": [0, 1, 2],
            COL_PRICE: [120.0, 100.0, 80.0],
            COL_CATEGORY_ID: [0, 0, 1],
        }
    ).with_columns(
        pl.col("listing_id").cast(pl.Int32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
    )

    result = compute_competitor_prices(df)

    assert "min_competitor_price" in result.columns, "column must be added"

    row_map = {
        row["listing_id"]: row["min_competitor_price"]
        for row in result.to_dicts()
    }
    # cat 0: min = 100 (listing 1)
    assert row_map[0] == pytest.approx(100.0), "listing 0 comp min = cat 0 min"
    assert row_map[1] == pytest.approx(100.0), "listing 1 comp min = cat 0 min (itself)"
    # cat 1: sole listing → min = 80 → Δ_comp = 0 → no undercut
    assert row_map[2] == pytest.approx(80.0), "sole listing comp min = its own price"


# ---------------------------------------------------------------------------
# 12.4-T1  high_delta_triggers_undercut — price decreases when Δ_comp > threshold
# ---------------------------------------------------------------------------


def test_high_delta_triggers_undercut() -> None:
    """
    Listing with price significantly above category min must decrease its price
    after apply_repricing_tick when Δ_comp > undercut_threshold.
    """
    # listing 0: price=120, competitor (listing 1) price=100
    # Δ_comp = (120-100)/120 = 0.167 > 0.05 → undercut must fire
    # listing 1: Δ_comp = (100-100)/100 = 0 → no undercut
    listings = _listings(
        prices=[120.0, 100.0],
        unit_costs=[30.0, 30.0],
        category_ids=[0, 0],
        demand_index=1.5,  # demand_index > 1.0 so MaxVolume would normally RISE
    )
    sellers = _sellers(2, strategy="MaxVolume", margin_floor=0.0, repricing_speed=1)
    cfg = _default_cfg(undercut_threshold=0.05)

    result = apply_repricing_tick(sellers, listings, tick=0, config=cfg)
    prices_before = listings[COL_PRICE].to_numpy()
    prices_after = result[COL_PRICE].to_numpy()

    # Listing 0 must be cheaper after the tick (undercut fired despite demand_index > 1)
    assert prices_after[0] < prices_before[0], (
        f"listing 0 price should decrease (undercut) but stayed {prices_before[0]} → {prices_after[0]}"
    )
    # Listing 1 was already the minimum → no undercut, demand > 1 → should stay or rise
    assert prices_after[1] >= prices_before[1] * 0.99, (
        f"listing 1 should not drop (already at cat min): {prices_before[1]} → {prices_after[1]}"
    )


def test_undercut_disabled_no_change_vs_baseline() -> None:
    """When competitor tracking is disabled, undercut has no effect vs baseline."""
    listings = _listings(
        prices=[120.0, 100.0],
        unit_costs=[30.0, 30.0],
        category_ids=[0, 0],
        demand_index=1.5,
    )
    sellers = _sellers(2, strategy="MaxVolume", margin_floor=0.0)
    cfg_on = _default_cfg(undercut_threshold=0.05)
    cfg_off = RepricingConfig(
        relative_step=0.02,
        min_listing_price=0.0,
        competitor=CompetitorTrackingConfig(enabled=False),
    )

    result_on = apply_repricing_tick(sellers, listings, tick=0, config=cfg_on)
    result_off = apply_repricing_tick(sellers, listings, tick=0, config=cfg_off)

    prices_on = result_on[COL_PRICE].to_numpy()
    prices_off = result_off[COL_PRICE].to_numpy()

    # With competitor disabled: listing 0 should rise (demand > 1, MaxVolume)
    # With competitor enabled:  listing 0 must drop (Δ_comp > threshold)
    assert prices_on[0] < prices_off[0], (
        "competitor undercut must lower price vs disabled-competitor baseline"
    )


# ---------------------------------------------------------------------------
# 12.4-T2  undercut_respects_unit_cost_guard — price ≥ unit_cost after undercut
# ---------------------------------------------------------------------------


def test_undercut_respects_unit_cost_guard() -> None:
    """
    Even when competitor price is extremely low, final listing price ≥ unit_cost.
    Verified via p_min floor (= unit_cost / (1 - fees)) applied in apply_repricing_tick.
    """
    # competitor price = 10 (far below any p_min)
    # Δ_comp large → undercut fires repeatedly, but p_min clips to safe floor
    listings = _listings(
        prices=[200.0, 10.0],   # listing 0 is expensive; listing 1 is competitor
        unit_costs=[50.0, 5.0],
        category_ids=[0, 0],
    )
    sellers = _sellers(
        2,
        strategy="MaxVolume",
        margin_floor=0.0,
        repricing_speed=1,
    )
    cfg = RepricingConfig(
        relative_step=0.20,   # large step to stress-test the floor
        min_listing_price=0.0,
        competitor=CompetitorTrackingConfig(enabled=True, undercut_threshold=0.01),
    )

    # Apply multiple ticks — keep stressing the floor
    result_df = listings
    for tick in range(10):
        result_df = apply_repricing_tick(sellers, result_df, tick=tick, config=cfg)

    result_prices = result_df[COL_PRICE].to_numpy()
    unit_costs = listings[COL_UNIT_COST].to_numpy()

    for i, (p, uc) in enumerate(zip(result_prices, unit_costs)):
        assert p >= uc, (
            f"listing {i}: price {p:.4f} < unit_cost {uc:.4f} — unit_cost guard violated"
        )


def test_category_id_preserved_through_repricing() -> None:
    """apply_repricing_tick must pass category_id through to output (required for next-tick ranking)."""
    listings = _listings(
        prices=[120.0, 100.0, 80.0],
        unit_costs=[30.0, 30.0, 20.0],
        category_ids=[0, 0, 1],
    )
    sellers = _sellers(3)
    cfg = _default_cfg()

    result = apply_repricing_tick(sellers, listings, tick=0, config=cfg)
    assert COL_CATEGORY_ID in result.columns, "category_id must survive apply_repricing_tick"
    assert result[COL_CATEGORY_ID].to_list() == listings[COL_CATEGORY_ID].to_list()
