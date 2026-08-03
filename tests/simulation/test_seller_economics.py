# Назначение файла: unit-тесты sellers_state_df и settle (Slice 8.2).
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_CAPITAL,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_GROSS_MARGIN,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    PRODUCTS_COLUMNS,
    SELLERS_STATE_COLUMNS,
    TRANSACTIONS_COLUMNS,
)
from market_abm.simulation.seller_economics import (
    filter_bankrupt_listings,
    init_sellers_state,
    new_bankruptcy_seller_ids,
    settle_seller_economics,
)
from market_abm.simulation.step import step


def _sellers_df(
    seller_ids: list[int],
    capitals: list[float],
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            COL_CAPITAL: capitals,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col(COL_CAPITAL).cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _sellers_state(
    seller_ids: list[int],
    capitals: list[float],
    *,
    bankrupt: list[bool] | None = None,
) -> pl.DataFrame:
    flags = bankrupt or [False] * len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_WORKING_CAPITAL: capitals,
            COL_IS_BANKRUPT: flags,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )


def _transactions(
    rows: list[tuple[int, int, int, float, float]],
) -> pl.DataFrame:
    """(tick_id, buyer_id, listing_id, price_paid, unit_cost) — seller_id = listing_id."""
    if not rows:
        return pl.DataFrame(
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
    tick_ids, buyer_ids, listing_ids, prices, costs = zip(*rows, strict=True)
    seller_ids = listing_ids
    return pl.DataFrame(
        {
            COL_TICK_ID: tick_ids,
            COL_BUYER_ID: buyer_ids,
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: seller_ids,
            COL_PRICE_PAID: prices,
            COL_UNIT_COST: costs,
            COL_GROSS_MARGIN: [p - c for p, c in zip(prices, costs, strict=True)],
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


def _buyers_df(n: int, *, freq: float = 1.0, budget: float = 500.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [budget] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [freq] * n,
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


def _products_df(
    seller_ids: list[int],
    prices: list[float],
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: seller_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )


def _step_config(**kwargs: object) -> SimulationStepConfig:
    defaults: dict[str, object] = {
        "tick_id": 1,
        "seed": 42,
        "choice": ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=10,
            outside_utility_bias=-100.0,
        ),
        "repricing": RepricingConfig.default_market(),
    }
    defaults.update(kwargs)
    return SimulationStepConfig(**defaults)


def test_init_sellers_state_copies_capital() -> None:
    sellers = _sellers_df([0, 1], [100.0, 250.0])
    state = init_sellers_state(sellers)

    assert state.columns == list(SELLERS_STATE_COLUMNS)
    assert state[COL_WORKING_CAPITAL].to_list() == [100.0, 250.0]
    assert state[COL_IS_BANKRUPT].to_list() == [False, False]


def test_settle_revenue_increases_capital() -> None:
    state = _sellers_state([0], [100.0])
    tx = _transactions([(1, 0, 0, 50.0, 20.0)])
    config = SellerEconomicsConfig(fixed_cost_per_tick=0.0)

    next_state = settle_seller_economics(state, tx, config)

    assert next_state[COL_WORKING_CAPITAL].item() == pytest.approx(130.0)
    assert next_state[COL_IS_BANKRUPT].item() is False


def test_settle_fixed_cost_bankrupts() -> None:
    state = _sellers_state([0], [3.0])
    tx = _transactions([])
    config = SellerEconomicsConfig(fixed_cost_per_tick=5.0)

    next_state = settle_seller_economics(state, tx, config)

    assert next_state[COL_IS_BANKRUPT].item() is True
    assert next_state[COL_WORKING_CAPITAL].item() == pytest.approx(-2.0)


def test_bankrupt_stays_bankrupt() -> None:
    state = _sellers_state([0], [500.0], bankrupt=[True])
    tx = _transactions([(1, 0, 0, 100.0, 10.0)])
    config = SellerEconomicsConfig(fixed_cost_per_tick=0.0)

    next_state = settle_seller_economics(state, tx, config)

    assert next_state[COL_IS_BANKRUPT].item() is True


def test_new_bankruptcy_seller_ids_detects_transition() -> None:
    prev = _sellers_state([0, 1], [10.0, 50.0])
    nxt = _sellers_state([0, 1], [-1.0, 50.0], bankrupt=[True, False])

    ids = new_bankruptcy_seller_ids(prev, nxt)

    assert ids == [0]


def test_filter_bankrupt_listings_excludes_seller() -> None:
    products = _products_df([0, 1], [100.0, 100.0])
    state = _sellers_state([0, 1], [10.0, 10.0], bankrupt=[True, False])

    filtered = filter_bankrupt_listings(products, state)

    assert filtered.height == 1
    assert filtered[COL_SELLER_ID].item() == 1


def test_bankrupt_seller_excluded_from_choice() -> None:
    buyers = _buyers_df(20, freq=1.0, budget=1000.0)
    sellers = _sellers_df([0, 1], [100.0, 100.0])
    products = _products_df([0, 1], [50.0, 200.0])
    state = _sellers_state([0, 1], [100.0, 100.0], bankrupt=[True, False])

    _, transactions, _, _ = step(
        buyers,
        sellers,
        products,
        _step_config(seed=99),
        sellers_state_df=state,
    )

    if transactions.height == 0:
        pytest.skip("no purchases in this random draw")
    assert 0 not in transactions[COL_SELLER_ID].to_list()


def test_step_backward_compat_without_sellers_state() -> None:
    buyers = _buyers_df(3)
    sellers = _sellers_df([0], [100.0])
    products = _products_df([0], [80.0])

    products_next, transactions, state_next, _ = step(
        buyers, sellers, products, _step_config(seed=1)
    )

    assert state_next is None
    assert products_next.height == products.height
    assert transactions.columns == list(TRANSACTIONS_COLUMNS)
