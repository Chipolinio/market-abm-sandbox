# Назначение файла: проверить сегментный outside_utility_bias по pvd_segment (Slice 004 §4.1).
# Базовая идея: разные сегменты покупателей получают разный bias отказа от покупки.
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from pydantic import ValidationError

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
    COL_PVD_SEGMENT,
    COL_RATING_VALUE,
    COL_SELLER_ID,
)
from market_abm.simulation.choice import (
    choose_listings_for_buyers,
    resolve_outside_utility_bias,
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


def _buyers_with_segments(
    buyer_ids: list[int],
    segments: list[str],
    *,
    budgets: float | list[float] = 500.0,
    beta_prices: float | list[float] = -0.2,
) -> pl.DataFrame:
    n = len(buyer_ids)
    if isinstance(budgets, (int, float)):
        budget_col = [float(budgets)] * n
    else:
        budget_col = list(budgets)
    if isinstance(beta_prices, (int, float)):
        beta_col = [float(beta_prices)] * n
    else:
        beta_col = list(beta_prices)
    return pl.DataFrame(
        {
            COL_BUYER_ID: buyer_ids,
            COL_BUDGET: budget_col,
            COL_BETA_PRICE: beta_col,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
            COL_PVD_SEGMENT: segments,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col(COL_PVD_SEGMENT).cast(pl.Categorical),
    )


def test_resolve_bias_scalar_fallback() -> None:
    buyers = _buyers_with_segments([0, 1], ["rich", "low"])
    cfg = ChoiceModelConfig(outside_utility_bias=-2.0)
    bias = resolve_outside_utility_bias(buyers, cfg)
    assert bias.dtype == np.float32
    np.testing.assert_array_equal(bias, np.array([-2.0, -2.0], dtype=np.float32))


def test_resolve_bias_per_segment() -> None:
    buyers = _buyers_with_segments([0, 1, 2], ["rich", "standard", "low"])
    cfg = ChoiceModelConfig(
        outside_utility_bias=-1.5,
        outside_utility_bias_by_pvd_segment={
            "rich": -3.0,
            "standard": -1.5,
            "low": 0.5,
        },
    )
    bias = resolve_outside_utility_bias(buyers, cfg)
    np.testing.assert_array_equal(
        bias,
        np.array([-3.0, -1.5, 0.5], dtype=np.float32),
    )


def test_unknown_segment_uses_scalar_fallback() -> None:
    buyers = _buyers_with_segments([0], ["rich"])
    cfg = ChoiceModelConfig(
        outside_utility_bias=-9.0,
        outside_utility_bias_by_pvd_segment={"standard": -1.0},
    )
    bias = resolve_outside_utility_bias(buyers, cfg)
    assert bias[0] == pytest.approx(-9.0)


def test_segment_bias_changes_purchase_rate() -> None:
    products = _products_df([60.0])
    buyers = _buyers_with_segments([0, 1, 2], ["rich", "standard", "low"])
    cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=-1.5,
        outside_utility_bias_by_pvd_segment={
            "rich": -200.0,
            "standard": -200.0,
            "low": 50.0,
        },
    )
    rng = np.random.default_rng(11)
    out = choose_listings_for_buyers(buyers, products, rng=rng, config=cfg)
    by_segment = dict(
        zip(
            buyers[COL_PVD_SEGMENT].to_list(),
            out[COL_LISTING_ID].to_list(),
            strict=True,
        )
    )
    assert by_segment["rich"] is not None
    assert by_segment["standard"] is not None
    assert by_segment["low"] is None


def test_config_rejects_unknown_segment_keys() -> None:
    with pytest.raises(ValidationError):
        ChoiceModelConfig(
            outside_utility_bias_by_pvd_segment={"vip": -1.0},
        )


def test_backward_compat_scalar_only() -> None:
    products = _products_df([50.0, 200.0])
    buyers = _buyers_with_segments([0], ["standard"])
    cfg_scalar = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=-100.0,
    )
    cfg_explicit_none = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=10,
        outside_utility_bias=-100.0,
        outside_utility_bias_by_pvd_segment=None,
    )
    seed = 42
    out_scalar = choose_listings_for_buyers(
        buyers, products, rng=np.random.default_rng(seed), config=cfg_scalar
    )
    out_none = choose_listings_for_buyers(
        buyers, products, rng=np.random.default_rng(seed), config=cfg_explicit_none
    )
    assert out_scalar.equals(out_none)


def test_resolve_bias_requires_pvd_segment_when_mapping_set() -> None:
    buyers = pl.DataFrame(
        {
            COL_BUYER_ID: [0],
            COL_BUDGET: [100.0],
            COL_BETA_PRICE: [-1.0],
            COL_BETA_DELIVERY: [-0.3],
            COL_BETA_RATING: [-0.5],
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
    )
    cfg = ChoiceModelConfig(
        outside_utility_bias_by_pvd_segment={"rich": -2.0},
    )
    with pytest.raises(ValueError, match=COL_PVD_SEGMENT):
        resolve_outside_utility_bias(buyers, cfg)
