# Spec 012.1, Slice 12.1.1: stock ledger + OOS hider + oversell clip.
# RED before: no stock_units / filter_in_stock in live step.
# GREEN after: inventory enabled → OOS before ranking; stock decrements; oversell clipped.

from __future__ import annotations

from unittest.mock import patch

import polars as pl
import pytest

from market_abm.config.inventory import InventoryConfig
from market_abm.config.ranking import RankingConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_CATEGORY_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STOCK_UNITS,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.inventory import (
    apply_stock_sales,
    clip_choices_to_stock,
    filter_in_stock,
)
from market_abm.simulation.ranking import compute_ranking_scores
from market_abm.simulation.step import step

_SEED = 42
_TICK = 1


def _inv_cfg(**kw: object) -> InventoryConfig:
    return InventoryConfig(enabled=True, **kw)


def _step_cfg(**kwargs: object) -> SimulationStepConfig:
    defaults: dict[str, object] = {
        "tick_id": _TICK,
        "seed": _SEED,
        "choice": ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=20,
            outside_utility_bias=-100.0,
            ranking=RankingConfig(top_k=5, organic_m=0, n_categories=2),
        ),
        "repricing": RepricingConfig.default_market(),
        "inventory": _inv_cfg(),
    }
    defaults.update(kwargs)
    return SimulationStepConfig(**defaults)


def _buyers_df(n: int, *, budget: float = 500.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [budget] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
    )


def _sellers_df(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            "capital": [10_000.0] * n,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _products(
    *,
    prices: list[float],
    stocks: list[int],
    category_ids: list[int] | None = None,
    ratings: list[float] | None = None,
) -> pl.DataFrame:
    n = len(prices)
    cats = category_ids if category_ids is not None else [0] * n
    rats = ratings if ratings is not None else [4.0] * n
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: rats,
            COL_CATEGORY_ID: cats,
            COL_STOCK_UNITS: stocks,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col(COL_STOCK_UNITS).cast(pl.Int32),
    )


# ---------------------------------------------------------------------------
# Unit helpers (pure) — also RED until inventory.py exists (imported above)
# ---------------------------------------------------------------------------


def test_filter_in_stock_drops_zero() -> None:
    products = _products(prices=[50.0, 60.0], stocks=[3, 0])
    out = filter_in_stock(products)
    assert out.height == 1
    assert out[COL_LISTING_ID].to_list() == [0]


def test_apply_stock_sales_decrements() -> None:
    products = _products(prices=[50.0, 60.0], stocks=[5, 2])
    tx = pl.DataFrame(
        {
            COL_LISTING_ID: [0, 0, 1],
            COL_BUYER_ID: [0, 1, 2],
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
    )
    out = apply_stock_sales(products, tx)
    assert out[COL_STOCK_UNITS].to_list() == [3, 1]


def test_clip_choices_to_stock_limits_purchases() -> None:
    products = _products(prices=[40.0], stocks=[1])
    choices = pl.DataFrame(
        {
            COL_BUYER_ID: [2, 0, 1],
            COL_LISTING_ID: [0, 0, 0],
            "choice_probability": [0.5, 0.5, 0.5],
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col("choice_probability").cast(pl.Float32),
    )
    clipped = clip_choices_to_stock(choices, products)
    kept = clipped.filter(pl.col(COL_LISTING_ID).is_not_null())
    assert kept.height == 1
    # Lowest buyer_id wins (deterministic)
    assert kept[COL_BUYER_ID].to_list() == [0]


# ---------------------------------------------------------------------------
# 12.1.1-T1  stock_decrements_on_sale
# ---------------------------------------------------------------------------


def test_stock_decrements_on_sale() -> None:
    buyers = _buyers_df(30)
    products = _products(prices=[40.0, 80.0], stocks=[100, 100])
    sellers = _sellers_df(2)
    cfg = _step_cfg()

    products_next, tx, _, _ = step(buyers, sellers, products, cfg)
    assert COL_STOCK_UNITS in products_next.columns
    assert tx.height > 0

    sales = (
        tx.group_by(COL_LISTING_ID)
        .len()
        .rename({"len": "n"})
        if tx.height
        else pl.DataFrame({COL_LISTING_ID: [], "n": []})
    )
    by_id = dict(
        zip(
            products_next[COL_LISTING_ID].to_list(),
            products_next[COL_STOCK_UNITS].to_list(),
            strict=True,
        )
    )
    for row in sales.iter_rows(named=True):
        lid = int(row[COL_LISTING_ID])
        assert by_id[lid] == 100 - int(row["n"])


# ---------------------------------------------------------------------------
# 12.1.1-T2  oos_listing_excluded_from_choice
# ---------------------------------------------------------------------------


def test_oos_listing_excluded_from_choice() -> None:
    buyers = _buyers_df(40)
    # listing 0 OOS; listing 1 in stock and cheaper/better for choice
    products = _products(
        prices=[30.0, 50.0],
        stocks=[0, 50],
        ratings=[5.0, 4.0],
        category_ids=[0, 0],
    )
    sellers = _sellers_df(2)
    _, tx, _, _ = step(buyers, sellers, products, _step_cfg())
    assert tx.height > 0
    assert 0 not in tx[COL_LISTING_ID].to_list()
    assert set(tx[COL_LISTING_ID].to_list()) <= {1}


# ---------------------------------------------------------------------------
# 12.1.1-T2b  oos_excluded_from_ranking_input
# ---------------------------------------------------------------------------


def test_oos_excluded_from_ranking_input() -> None:
    buyers = _buyers_df(20)
    products = _products(
        prices=[40.0, 45.0, 50.0],
        stocks=[0, 10, 10],
        category_ids=[0, 0, 1],
    )
    sellers = _sellers_df(3)
    seen_ids: list[list[int]] = []

    real_compute = compute_ranking_scores

    def _spy(products_df: pl.DataFrame, *args, **kwargs):
        seen_ids.append(products_df[COL_LISTING_ID].to_list())
        return real_compute(products_df, *args, **kwargs)

    with patch(
        "market_abm.simulation.step.compute_ranking_scores",
        side_effect=_spy,
    ):
        step(buyers, sellers, products, _step_cfg())

    assert seen_ids, "ranking must be called"
    assert 0 not in seen_ids[0], "OOS listing must not enter compute_ranking_scores"
    assert set(seen_ids[0]) <= {1, 2}


# ---------------------------------------------------------------------------
# 12.1.1-T3  demand_spills_to_competitor
# ---------------------------------------------------------------------------


def test_demand_spills_to_competitor() -> None:
    buyers = _buyers_df(60)
    # Same category: A (listing 0) preferred when in stock; B (listing 1) competitor
    products_both = _products(
        prices=[35.0, 40.0],
        stocks=[50, 50],
        ratings=[5.0, 4.5],
        category_ids=[0, 0],
    )
    products_oos_a = _products(
        prices=[35.0, 40.0],
        stocks=[0, 50],
        ratings=[5.0, 4.5],
        category_ids=[0, 0],
    )
    sellers = _sellers_df(2)
    cfg = _step_cfg()

    _, tx_both, _, _ = step(buyers, sellers, products_both, cfg)
    _, tx_spill, _, _ = step(buyers, sellers, products_oos_a, cfg)

    share_b_both = (
        (tx_both[COL_LISTING_ID] == 1).sum() / tx_both.height if tx_both.height else 0.0
    )
    share_b_spill = (
        (tx_spill[COL_LISTING_ID] == 1).sum() / tx_spill.height if tx_spill.height else 0.0
    )
    assert tx_spill.height > 0
    assert share_b_spill > share_b_both, (
        f"OOS of A must spill demand to B: both={share_b_both:.3f} spill={share_b_spill:.3f}"
    )


# ---------------------------------------------------------------------------
# 12.1.1-T4  oversell_clipped_to_stock
# ---------------------------------------------------------------------------


def test_oversell_clipped_to_stock() -> None:
    buyers = _buyers_df(40)
    products = _products(prices=[40.0], stocks=[1])
    sellers = _sellers_df(1)
    products_next, tx, _, _ = step(buyers, sellers, products, _step_cfg())

    assert tx.height <= 1
    assert products_next[COL_STOCK_UNITS].to_list() == [0] or (
        tx.height == 0 and products_next[COL_STOCK_UNITS].to_list() == [1]
    )
    if tx.height == 1:
        assert products_next[COL_STOCK_UNITS].to_list() == [0]
