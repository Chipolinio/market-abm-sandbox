# Назначение файла: проверить выбор оффера покупателем в одном шаге симуляции.
# Базовая идея: бюджет, beta и outside option должны влиять на результат предсказуемо.
from __future__ import annotations

import warnings

import numpy as np
import polars as pl
import pytest

from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_LISTING_ID,
    COL_PRICE,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)
from market_abm.simulation.choice import (
    choose_listings_for_all_buyers,
    choose_listings_for_buyers,
)


def _products_df(prices: list[float]) -> pl.DataFrame:
    n = len(prices)
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            "unit_cost": [10.0] * n,
            COL_PRICE: prices,
            "demand_index": [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col("unit_cost").cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col("demand_index").cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    )


def _buyers_df(
    buyer_ids: list[int],
    budgets: list[float],
    beta_prices: list[float],
) -> pl.DataFrame:
    n = len(buyer_ids)
    return pl.DataFrame(
        {
            COL_BUYER_ID: buyer_ids,
            COL_BUDGET: budgets,
            COL_BETA_PRICE: beta_prices,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
    )


def test_negative_beta_price_prefers_cheaper_listing() -> None:
    products = _products_df([50.0, 200.0])
    buyers = _buyers_df([0], [500.0], [-0.2])
    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=-100.0,
    )
    rng = np.random.default_rng(0)
    out = choose_listings_for_buyers(buyers, products, rng=rng, config=cfg)
    assert out[COL_LISTING_ID].item() == 0


def test_budget_filter_excludes_expensive_listings() -> None:
    products = _products_df([30.0, 40.0, 1000.0])
    buyers = _buyers_df([0], [50.0], [-1.0])
    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=-500.0,
    )
    rng = np.random.default_rng(1)
    out = choose_listings_for_buyers(buyers, products, rng=rng, config=cfg)
    assert out[COL_LISTING_ID].item() in {0, 1}


def test_high_outside_bias_can_yield_no_purchase() -> None:
    products = _products_df([80.0, 90.0])
    buyers = _buyers_df([0], [100.0], [-0.1])
    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=10.0,
    )
    rng = np.random.default_rng(2)
    out = choose_listings_for_buyers(buyers, products, rng=rng, config=cfg)
    assert out[COL_LISTING_ID].item() is None


def test_one_row_per_buyer_in_batch() -> None:
    products = _products_df([10.0, 20.0, 30.0, 40.0])
    buyers = _buyers_df([0, 1, 2], [100.0, 100.0, 100.0], [-1.0, -1.0, -1.0])
    cfg = ChoiceModelConfig(engine="numpy_softmax", max_products_per_choice_set=4)
    rng = np.random.default_rng(3)
    out = choose_listings_for_buyers(buyers, products, rng=rng, config=cfg)
    assert out.height == 3
    assert out[COL_BUYER_ID].n_unique() == 3


def test_batched_and_single_pass_match_on_small_set() -> None:
    products = _products_df([15.0, 25.0, 35.0, 45.0, 55.0])
    buyer_ids = list(range(120))
    buyers = _buyers_df(buyer_ids, [200.0] * 120, [-1.5] * 120)
    seed = 99
    single_cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=5,
        buyers_batch_size=10_000,
        outside_utility_bias=-500.0,
    )
    batched_cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=5,
        buyers_batch_size=101,
        outside_utility_bias=-500.0,
    )
    single = choose_listings_for_all_buyers(
        buyers, products, seed=seed, config=single_cfg
    )
    batched = choose_listings_for_all_buyers(
        buyers, products, seed=seed, config=batched_cfg
    )
    assert single.sort(COL_BUYER_ID).equals(batched.sort(COL_BUYER_ID))


def test_choice_learn_engine_falls_back_when_unavailable() -> None:
    import importlib.util

    if importlib.util.find_spec("choice_learn") is not None:
        pytest.skip("choice_learn is installed in this environment")

    products = _products_df([20.0, 30.0])
    buyers = _buyers_df([0], [100.0], [-1.0])
    cfg = ChoiceModelConfig(engine="choice_learn", max_products_per_choice_set=5)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = choose_listings_for_all_buyers(
            buyers, products, seed=7, config=cfg, allow_choice_learn_fallback=True
        )
    assert out.height == 1
    assert any("choice_learn" in str(w.message).lower() for w in caught)
