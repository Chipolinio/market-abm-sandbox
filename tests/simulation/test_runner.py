# Назначение файла: проверить много-тиковый генератор run_simulation (Slice 004 §4.2).
# Базовая идея: ленивый цикл step, bootstrap listings→products, rechunk guard.
from __future__ import annotations

from unittest.mock import patch

import polars as pl
import pytest

from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import SimulationRunConfig
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
    LISTINGS_COLUMNS,
    LISTINGS_SCHEMA_DTYPES,
    PRODUCTS_COLUMNS,
    PRODUCTS_SCHEMA_DTYPES,
)
from market_abm.simulation.runner import (
    PRODUCTS_RECHUNK_N_CHUNKS_THRESHOLD,
    _bootstrap_products_from_listings,
    _bootstrap_rng,
    _maybe_rechunk_products,
    run_simulation,
)
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


def _sellers_df(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            "capital": [100.0] * n,
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


def _listings_df(n: int, *, prices: float = 80.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: [prices] * n,
            COL_DEMAND_INDEX: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )


def _run_config(*, seed: int = 42) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=10,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
    )


def test_run_simulation_yield_count() -> None:
    buyers = _buyers_df(8)
    sellers = _sellers_df(3)
    listings = _listings_df(3)
    config = _run_config()
    results = list(run_simulation(buyers, sellers, listings, n_ticks=5, config=config))
    assert len(results) == 5
    assert [tick_id for tick_id, _, _ in results] == [0, 1, 2, 3, 4]


def test_run_simulation_lazy_evaluation() -> None:
    buyers = _buyers_df(2)
    sellers = _sellers_df(1)
    listings = _listings_df(1)
    config = _run_config()
    with patch("market_abm.simulation.runner.step") as mock_step:
        products = _bootstrap_products_from_listings(
            listings,
            config=config.products_bootstrap,
            rng=_bootstrap_rng(config.seed),
        )
        mock_step.return_value = (products, pl.DataFrame(), None, None)
        gen = run_simulation(buyers, sellers, listings, n_ticks=3, config=config)
        assert mock_step.call_count == 0
        next(gen)
        assert mock_step.call_count == 1
        next(gen)
        assert mock_step.call_count == 2


def test_run_simulation_matches_manual_steps() -> None:
    buyers = _buyers_df(20, freq=1.0)
    sellers = _sellers_df(4)
    listings = _listings_df(4)
    config = _run_config(seed=7)
    n_ticks = 3

    rng = _bootstrap_rng(config.seed)
    products = _bootstrap_products_from_listings(
        listings, config=config.products_bootstrap, rng=rng
    )
    manual: list[tuple[int, pl.DataFrame, pl.DataFrame]] = []
    for tick_id in range(n_ticks):
        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=config.seed,
            choice=config.choice,
            repricing=config.repricing,
        )
        products, transactions, _, _ = step(buyers, sellers, products, step_config)
        products = _maybe_rechunk_products(products)
        manual.append((tick_id, products.clone(), transactions.clone()))

    generated = list(
        run_simulation(buyers, sellers, listings, n_ticks=n_ticks, config=config)
    )
    assert len(generated) == n_ticks
    for (tick_id, prod, tx), (m_tick, m_prod, m_tx) in zip(generated, manual, strict=True):
        assert tick_id == m_tick
        assert prod.equals(m_prod)
        assert tx.equals(m_tx)


def test_run_simulation_does_not_mutate_inputs() -> None:
    buyers = _buyers_df(3)
    sellers = _sellers_df(2)
    listings = _listings_df(2)
    config = _run_config()
    buyers_before = buyers.clone()
    sellers_before = sellers.clone()
    listings_before = listings.clone()
    list(run_simulation(buyers, sellers, listings, n_ticks=2, config=config))
    assert buyers.equals(buyers_before)
    assert sellers.equals(sellers_before)
    assert listings.equals(listings_before)


def test_run_simulation_preserves_card_features() -> None:
    """
    delivery_days must remain constant across ticks (bootstrap-only field).
    rating_value is now dynamic (EMA from Spec 012 §6) — check range [1, 5] only.
    """
    buyers = _buyers_df(15, freq=1.0)
    sellers = _sellers_df(3)
    listings = _listings_df(3)
    config = _run_config(seed=99)
    delivery_at_tick0: pl.DataFrame | None = None
    for tick_id, products, _ in run_simulation(
        buyers, sellers, listings, n_ticks=3, config=config
    ):
        delivery = products.select([COL_LISTING_ID, COL_DELIVERY_DAYS])
        ratings = products[COL_RATING_VALUE].to_numpy()
        if tick_id == 0:
            delivery_at_tick0 = delivery.clone()
        else:
            assert delivery_at_tick0 is not None
            assert delivery.equals(delivery_at_tick0), "delivery_days must not change"
        # rating_value is dynamic post-012 §6; validate range only
        assert all(1.0 <= r <= 5.0 for r in ratings), f"tick {tick_id}: ratings out of range: {ratings}"


def test_run_simulation_invalid_n_ticks() -> None:
    buyers = _buyers_df(1)
    sellers = _sellers_df(1)
    listings = _listings_df(1)
    config = _run_config()
    with pytest.raises(ValueError, match="n_ticks"):
        list(run_simulation(buyers, sellers, listings, n_ticks=0, config=config))


def test_run_simulation_empty_listings() -> None:
    buyers = _buyers_df(2)
    sellers = _sellers_df(1)
    schema = {name: getattr(pl, dtype) for name, dtype in LISTINGS_SCHEMA_DTYPES.items()}
    listings = pl.DataFrame({col: [] for col in LISTINGS_COLUMNS}, schema=schema)
    config = _run_config()
    results = list(run_simulation(buyers, sellers, listings, n_ticks=2, config=config))
    assert len(results) == 2
    for _, products, transactions in results:
        assert products.height == 0
        assert transactions.height == 0


def test_run_simulation_rechunk_caps_chunks() -> None:
    buyers = _buyers_df(30, freq=1.0)
    sellers = _sellers_df(5)
    listings = _listings_df(5)
    config = _run_config(seed=123)
    for _, products, _ in run_simulation(
        buyers, sellers, listings, n_ticks=50, config=config
    ):
        assert products.n_chunks() <= PRODUCTS_RECHUNK_N_CHUNKS_THRESHOLD
