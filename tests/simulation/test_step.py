# Назначение файла: проверить один шаг симуляции step(...) для Slice 003.
# Базовая идея: step возвращает обновленные products и transactions с корректными связями.
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.repricing import RepricingConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
    PRODUCTS_COLUMNS,
    PRODUCTS_SCHEMA_DTYPES,
    TRANSACTIONS_COLUMNS,
)
from market_abm.simulation.repricing import min_price_from_margin
from market_abm.simulation.step import step


def _buyers_df(n: int, *, freq: float = 1.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [500.0] * n,
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


def _sellers_df(
    seller_ids: list[int],
    strategies: list[str],
    *,
    speeds: list[int] | None = None,
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: strategies,
            "capital": [100.0] * n,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: speeds or [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _products_df(
    seller_ids: list[int],
    prices: list[float],
    *,
    demands: list[float] | None = None,
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: seller_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: demands or [1.0] * n,
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
    defaults = {
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


def test_step_returns_products_and_transactions_with_expected_columns() -> None:
    buyers = _buyers_df(5)
    sellers = _sellers_df([0], ["MaxProfit"])
    products = _products_df([0], [100.0])
    products_next, transactions, _ = step(buyers, sellers, products, _step_config())
    assert products_next.height == products.height
    assert products_next.columns == list(PRODUCTS_COLUMNS)
    assert transactions.columns == list(TRANSACTIONS_COLUMNS)


def test_transactions_reference_valid_buyer_and_listing_ids() -> None:
    buyers = _buyers_df(3)
    sellers = _sellers_df([0], ["MaxProfit"])
    products = _products_df([0], [50.0])
    _, transactions, _ = step(buyers, sellers, products, _step_config(seed=7))
    if transactions.height == 0:
        pytest.skip("no purchases in this random draw")
    assert set(transactions[COL_BUYER_ID].to_list()).issubset(set(buyers[COL_BUYER_ID].to_list()))
    assert set(transactions[COL_LISTING_ID].to_list()).issubset(set(products[COL_LISTING_ID].to_list()))


def test_step_prices_stay_above_floor() -> None:
    buyers = _buyers_df(10)
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxVolume"])
    products = _products_df([0, 1], [100.0, 100.0])
    products_next, _, _ = step(buyers, sellers, products, _step_config(seed=11))
    joined = products_next.join(
        sellers.select([COL_SELLER_ID, COL_MARGIN_FLOOR]),
        on=COL_SELLER_ID,
        how="left",
    )
    p_min = joined.select(
        min_price_from_margin(pl.col(COL_UNIT_COST), pl.col(COL_MARGIN_FLOOR)).alias("p_min")
    )["p_min"]
    assert (products_next[COL_PRICE] >= p_min).all()


def test_demand_index_uses_normalized_sales_formula() -> None:
    buyers = _buyers_df(100, freq=1.0)
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxProfit"])
    products = _products_df([0, 1], [30.0, 200.0])
    cfg = _step_config(seed=5)
    products_next, transactions, _ = step(buyers, sellers, products, cfg)
    n_active = buyers.height
    expected = n_active / products.height
    sales = (
        transactions.group_by(COL_LISTING_ID)
        .len()
        .rename({"len": "sales_count"})
        if transactions.height > 0
        else pl.DataFrame({COL_LISTING_ID: [], "sales_count": []}).with_columns(
            pl.col(COL_LISTING_ID).cast(pl.Int32),
            pl.col("sales_count").cast(pl.UInt32),
        )
    )
    expected_demand = (
        products.select(COL_LISTING_ID)
        .join(sales, on=COL_LISTING_ID, how="left")
        .with_columns(pl.col("sales_count").fill_null(0))
        .with_columns((pl.col("sales_count") / expected).alias("expected_demand"))
    )
    joined = products_next.select([COL_LISTING_ID, COL_DEMAND_INDEX]).join(
        expected_demand.select([COL_LISTING_ID, "expected_demand"]),
        on=COL_LISTING_ID,
        how="left",
    )
    assert joined[COL_DEMAND_INDEX].to_list() == pytest.approx(
        joined["expected_demand"].to_list()
    )


def test_rules_repricing_respects_warmup_ticks() -> None:
    buyers = _buyers_df(50, freq=1.0)
    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxVolume"], speeds=[1, 1])
    products = _products_df([0, 1], [100.0, 100.0], demands=[0.0, 0.0])
    cfg = _step_config(
        seed=3,
        tick_id=2,
        repricing=RepricingConfig.default_market().model_copy(update={"warmup_ticks": 5}),
    )
    products_next, _, _ = step(buyers, sellers, products, cfg)
    assert products_next[COL_PRICE].to_list() == pytest.approx(products[COL_PRICE].to_list())


def test_rating_maximizer_price_unchanged_on_active_tick() -> None:
    buyers = _buyers_df(50, freq=1.0)
    sellers = _sellers_df([0, 1], ["RatingMaximizer", "MaxProfit"], speeds=[1, 1])
    products = _products_df([0, 1], [100.0, 100.0], demands=[1.5, 1.5])
    cfg = _step_config(seed=3, tick_id=1)
    products_next, _, _ = step(buyers, sellers, products, cfg)
    rating_price = products_next.filter(pl.col(COL_SELLER_ID) == 0)[COL_PRICE].item()
    assert rating_price == pytest.approx(100.0)


def test_empty_products_returns_empty_transactions() -> None:
    buyers = _buyers_df(2)
    sellers = _sellers_df([0], ["MaxProfit"])
    schema = {name: getattr(pl, dtype) for name, dtype in PRODUCTS_SCHEMA_DTYPES.items()}
    products = pl.DataFrame({col: [] for col in PRODUCTS_COLUMNS}, schema=schema)
    products_next, transactions, _ = step(buyers, sellers, products, _step_config())
    assert products_next.height == 0
    assert transactions.height == 0


def test_step_does_not_mutate_input_frames() -> None:
    buyers = _buyers_df(3)
    sellers = _sellers_df([0], ["MaxProfit"])
    products = _products_df([0], [80.0])
    buyers_before = buyers.clone()
    sellers_before = sellers.clone()
    products_before = products.clone()
    step(buyers, sellers, products, _step_config(seed=1))
    assert buyers.equals(buyers_before)
    assert sellers.equals(sellers_before)
    assert products.equals(products_before)
