# Spec 012.1, Slice 12.1.3: replenishment lead time + prepaid COGS + holding.
# RED→GREEN: advance_replenishment, bootstrap prepaid, settle mode C.

from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.inventory import InventoryConfig, ReplenishmentConfig
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
    COL_INBOUND_ETA_TICKS,
    COL_INBOUND_UNITS,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
    COL_STRATEGY_TYPE,
    COL_GROSS_MARGIN,
    COL_TICK_ID,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    TRANSACTIONS_COLUMNS,
)
from market_abm.simulation.inventory import (
    advance_replenishment,
    apply_bootstrap_stock_prepaid,
    compute_holding_by_seller,
)
from market_abm.simulation.seller_economics import (
    init_sellers_state,
    settle_seller_economics,
)
from market_abm.simulation.step import step

_SEED = 42


def _repl_cfg(**kw: object) -> ReplenishmentConfig:
    return ReplenishmentConfig(enabled=True, **kw)


def _step_cfg(**kwargs: object) -> SimulationStepConfig:
    defaults: dict[str, object] = {
        "tick_id": 1,
        "seed": _SEED,
        "choice": ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=20,
            outside_utility_bias=-100.0,
            ranking=RankingConfig(top_k=5, organic_m=0, n_categories=2),
        ),
        "repricing": RepricingConfig.default_market(),
        "inventory": InventoryConfig(enabled=True),
        "replenishment": _repl_cfg(
            reorder_point=10,
            reorder_quantity=40,
            lead_time_ticks=3,
            holding_cost_per_unit_tick=0.0,
        ),
        "economics": SellerEconomicsConfig(fixed_cost_per_tick=0.0),
    }
    defaults.update(kwargs)
    return SimulationStepConfig(**defaults)


def _buyers_df(n: int = 1, *, budget: float = 500.0) -> pl.DataFrame:
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
            COL_PURCHASE_FREQUENCY: [0.0] * n,  # no purchases by default
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


def _sellers_df(*, capital: float = 10_000.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: [0],
            COL_STRATEGY_TYPE: ["MaxProfit"],
            "capital": [capital],
            COL_MARGIN_FLOOR: [0.2],
            COL_REPRICING_SPEED: [1],
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _sellers_state(*, capital: float = 10_000.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: [0],
            COL_WORKING_CAPITAL: [capital],
            COL_IS_BANKRUPT: [False],
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )


def _products(
    *,
    stock: int = 5,
    unit_cost: float = 10.0,
    price: float = 50.0,
) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: [0],
            COL_SELLER_ID: [0],
            COL_PRICE: [price],
            COL_UNIT_COST: [unit_cost],
            COL_DELIVERY_DAYS: [2],
            COL_RATING_VALUE: [4.5],
            COL_DEMAND_INDEX: [0.0],
            COL_CATEGORY_ID: [0],
            COL_STOCK_UNITS: [stock],
            COL_STOCK_TARGET: [50],
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Int32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_CATEGORY_ID).cast(pl.Int32),
        pl.col(COL_STOCK_UNITS).cast(pl.Int32),
        pl.col(COL_STOCK_TARGET).cast(pl.Int32),
    )


def test_12_1_3_t1_reorder_reduces_capital_immediately() -> None:
    """capital↓ at order tick before stock arrives."""
    products = _products(stock=5, unit_cost=10.0)
    state = _sellers_state(capital=1_000.0)
    cfg = _repl_cfg(reorder_point=10, reorder_quantity=40, lead_time_ticks=5)

    products_next, state_next = advance_replenishment(products, state, cfg)

    order_cost = 40 * 10.0
    assert products_next[COL_INBOUND_UNITS].item() == 40
    assert products_next[COL_INBOUND_ETA_TICKS].item() == 5
    assert products_next[COL_STOCK_UNITS].item() == 5  # not yet arrived
    assert state_next[COL_WORKING_CAPITAL].item() == pytest.approx(1_000.0 - order_cost)


def test_12_1_3_t2_stock_arrives_after_lead_time() -> None:
    """After lead_time ticks, inbound lands in stock_units."""
    products = _products(stock=5, unit_cost=10.0)
    state = _sellers_state(capital=1_000.0)
    cfg = _repl_cfg(reorder_point=10, reorder_quantity=40, lead_time_ticks=3)

    products, state = advance_replenishment(products, state, cfg)
    assert products[COL_INBOUND_UNITS].item() == 40
    assert products[COL_STOCK_UNITS].item() == 5

    for _ in range(3):
        products, state = advance_replenishment(products, state, cfg)

    assert products[COL_INBOUND_UNITS].item() == 0
    assert products[COL_STOCK_UNITS].item() == 5 + 40


def test_12_1_3_t3_cash_gap_can_bankrupt() -> None:
    """Large prepaid order leaves thin capital; fixed+holding → bankrupt."""
    products = _products(stock=5, unit_cost=10.0)
    # Order 40*10=400 → capital 50; then fixed 30 + holding 5*5=25 → bankrupt
    state = _sellers_state(capital=450.0)
    cfg = _repl_cfg(
        reorder_point=10,
        reorder_quantity=40,
        lead_time_ticks=5,
        holding_cost_per_unit_tick=5.0,
    )
    products, state = advance_replenishment(products, state, cfg)
    assert state[COL_WORKING_CAPITAL].item() == pytest.approx(50.0)

    holding = compute_holding_by_seller(
        products, holding_cost_per_unit_tick=cfg.holding_cost_per_unit_tick
    )
    empty_tx = pl.DataFrame(
        {col: [] for col in TRANSACTIONS_COLUMNS},
        schema={
            COL_TICK_ID: pl.Int32,
            COL_BUYER_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_PRICE_PAID: pl.Float32,
            COL_UNIT_COST: pl.Float32,
            COL_GROSS_MARGIN: pl.Float32,
        },
    )
    next_state = settle_seller_economics(
        state,
        empty_tx,
        SellerEconomicsConfig(fixed_cost_per_tick=30.0),
        prepaid_cogs=True,
        holding_by_seller=holding,
    )
    assert next_state[COL_IS_BANKRUPT].item() is True


def test_12_1_3_t4_replenishment_disabled_noop() -> None:
    products = _products(stock=5)
    state = _sellers_state(capital=1_000.0)
    cfg = ReplenishmentConfig(enabled=False, reorder_point=10, reorder_quantity=40)

    products_next, state_next = advance_replenishment(products, state, cfg)

    assert COL_INBOUND_UNITS not in products_next.columns
    assert state_next[COL_WORKING_CAPITAL].item() == pytest.approx(1_000.0)
    assert products_next[COL_STOCK_UNITS].item() == 5


def test_12_1_3_t5_bootstrap_stock_prepaid_at_init() -> None:
    sellers = _sellers_df(capital=1_000.0)
    products = _products(stock=20, unit_cost=10.0)
    state = init_sellers_state(sellers)

    state_prepaid = apply_bootstrap_stock_prepaid(state, products)

    assert state_prepaid[COL_WORKING_CAPITAL].item() == pytest.approx(1_000.0 - 20 * 10.0)


def test_12_1_3_t6_sale_of_prepaid_stock_revenue_only() -> None:
    """settle mode C: Δcapital ≈ +price_paid − fixed, no second COGS."""
    state = _sellers_state(capital=500.0)
    tx = pl.DataFrame(
        {
            COL_TICK_ID: [1],
            COL_BUYER_ID: [0],
            COL_LISTING_ID: [0],
            COL_SELLER_ID: [0],
            COL_PRICE_PAID: [80.0],
            COL_UNIT_COST: [30.0],
            COL_GROSS_MARGIN: [50.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )
    next_state = settle_seller_economics(
        state,
        tx,
        SellerEconomicsConfig(fixed_cost_per_tick=5.0),
        prepaid_cogs=True,
    )
    # 500 + 80 - 0 cogs - 5 fixed = 575 (legacy would be 500+80-30-5=545)
    assert next_state[COL_WORKING_CAPITAL].item() == pytest.approx(575.0)


def test_12_1_3_t0_legacy_settle_when_replenishment_disabled() -> None:
    """Spec 008 regress: prepaid_cogs=False → revenue − cogs − fixed."""
    state = _sellers_state(capital=100.0)
    tx = pl.DataFrame(
        {
            COL_TICK_ID: [1],
            COL_BUYER_ID: [0],
            COL_LISTING_ID: [0],
            COL_SELLER_ID: [0],
            COL_PRICE_PAID: [50.0],
            COL_UNIT_COST: [20.0],
            COL_GROSS_MARGIN: [30.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )
    next_state = settle_seller_economics(
        state,
        tx,
        SellerEconomicsConfig(fixed_cost_per_tick=0.0),
        prepaid_cogs=False,
    )
    assert next_state[COL_WORKING_CAPITAL].item() == pytest.approx(130.0)


def test_12_1_3_step_wires_reorder() -> None:
    """Live step with replenishment.enabled places inbound and cuts capital."""
    buyers = _buyers_df(1)
    sellers = _sellers_df(capital=1_000.0)
    products = _products(stock=5, unit_cost=10.0)
    state = _sellers_state(capital=1_000.0)
    cfg = _step_cfg(
        replenishment=_repl_cfg(
            reorder_point=10,
            reorder_quantity=40,
            lead_time_ticks=3,
            holding_cost_per_unit_tick=0.0,
        ),
        economics=SellerEconomicsConfig(fixed_cost_per_tick=0.0),
    )

    products_next, _, state_next, _ = step(
        buyers, sellers, products, cfg, sellers_state_df=state
    )

    assert state_next is not None
    assert products_next[COL_INBOUND_UNITS].item() == 40
    assert products_next[COL_STOCK_UNITS].item() == 5
    assert state_next[COL_WORKING_CAPITAL].item() == pytest.approx(600.0)
