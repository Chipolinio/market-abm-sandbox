# Spec 010 §10.3 — income utility γ·log(budget/budget_baseline) в choice MNL.
from __future__ import annotations

import polars as pl

from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUYER_ID,
    COL_DELIVERY_DAYS,
    COL_LISTING_ID,
    COL_PRICE,
    COL_CHOICE_PROBABILITY,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)
from market_abm.simulation.choice import choose_listings_for_all_buyers


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


def _buyers_df(budget: float, baseline: float) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: [0],
            COL_BUDGET: [budget],
            COL_BUDGET_BASELINE: [baseline],
            COL_BETA_PRICE: [-0.2],
            COL_BETA_DELIVERY: [-0.3],
            COL_BETA_RATING: [-0.5],
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BUDGET_BASELINE).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
    )


def _conversion_rate(
    buyers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    config: ChoiceModelConfig,
    *,
    seed: int,
    n_trials: int = 200,
) -> float:
    purchases = 0
    for trial in range(n_trials):
        choices = choose_listings_for_all_buyers(
            buyers_df,
            products_df,
            seed=seed + trial,
            config=config,
        )
        if choices[COL_LISTING_ID][0] is not None:
            purchases += 1
    return purchases / n_trials


def test_income_term_reduces_conversion_at_fixed_prices() -> None:
    products = _products_df([50.0, 50.0])
    config = ChoiceModelConfig(
        engine="numpy_softmax",
        outside_utility_bias=-13.1,
        income_utility_gamma=0.5,
        max_products_per_choice_set=10,
        buyers_batch_size=500,
    )
    rich = _buyers_df(200.0, 200.0)
    poor = _buyers_df(100.0, 200.0)

    rich_rate = _conversion_rate(rich, products, config, seed=1)
    poor_rate = _conversion_rate(poor, products, config, seed=1)

    assert rich_rate > poor_rate
    assert poor_rate < 1.0


def test_gamma_zero_disables_income_channel() -> None:
    products = _products_df([50.0])
    config = ChoiceModelConfig(
        engine="numpy_softmax",
        outside_utility_bias=-20.0,
        income_utility_gamma=0.0,
        max_products_per_choice_set=10,
        buyers_batch_size=500,
    )
    full = _buyers_df(500.0, 500.0)
    half = _buyers_df(250.0, 500.0)

    full_choices = choose_listings_for_all_buyers(full, products, seed=42, config=config)
    half_choices = choose_listings_for_all_buyers(half, products, seed=42, config=config)

    assert full_choices.equals(half_choices)


def test_income_shift_is_scalar_on_all_products() -> None:
    products = _products_df([40.0, 40.0])
    config = ChoiceModelConfig(
        engine="numpy_softmax",
        outside_utility_bias=-20.0,
        income_utility_gamma=0.5,
        max_products_per_choice_set=10,
        buyers_batch_size=500,
    )
    rich = _buyers_df(200.0, 200.0)
    poor = _buyers_df(100.0, 200.0)

    rich_choices = choose_listings_for_all_buyers(rich, products, seed=7, config=config)
    poor_choices = choose_listings_for_all_buyers(poor, products, seed=7, config=config)

    assert rich_choices[COL_LISTING_ID][0] is not None
    assert poor_choices[COL_LISTING_ID][0] is not None
    assert rich_choices[COL_LISTING_ID][0] == poor_choices[COL_LISTING_ID][0]
    assert rich_choices[COL_CHOICE_PROBABILITY][0] > poor_choices[COL_CHOICE_PROBABILITY][0]
