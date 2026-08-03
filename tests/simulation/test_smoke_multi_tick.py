# Назначение файла: smoke-тест полного цикла на 2–3 тика (Slice 003 §3.4).
# Базовая идея: buyers + sellers + products проходят step(...) несколько раз без падений.
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.domain.constants import (
    COL_DELIVERY_DAYS,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
    PRODUCTS_COLUMNS,
    TRANSACTIONS_COLUMNS,
)
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.repricing import min_price_from_margin
from market_abm.simulation.step import step


def _listings_to_products(listings: pl.DataFrame, *, seed: int) -> pl.DataFrame:
    """Добавляет поля карточки к listings_df и собирает products_df."""
    rng = np.random.default_rng(seed)
    n = listings.height
    return listings.with_columns(
        pl.Series(COL_DELIVERY_DAYS, rng.uniform(1.0, 7.0, size=n), dtype=pl.Float32),
        pl.Series(COL_RATING_VALUE, rng.uniform(3.0, 5.0, size=n), dtype=pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


def test_smoke_three_ticks_end_to_end() -> None:
    seed = 42
    n_buyers = 500
    n_sellers = 80

    buyers = generate_buyers(
        BuyerPopulationConfig.default_market(n_buyers=n_buyers, seed=seed)
    )
    sellers = generate_sellers(
        SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
    )
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=seed,
    )
    products = _listings_to_products(listings, seed=seed)

    choice_cfg = ChoiceModelConfig(
        engine="numpy_softmax",
        max_products_per_choice_set=50,
        buyers_batch_size=500,
        outside_utility_bias=-100.0,
    )
    repricing_cfg = RepricingConfig.default_market()

    total_transactions = 0
    for tick_id in (0, 1, 2):
        config = SimulationStepConfig(
            tick_id=tick_id,
            seed=seed,
            choice=choice_cfg,
            repricing=repricing_cfg,
        )
        products, transactions, _ = step(buyers, sellers, products, config)

        assert products.height == n_sellers
        # Spec 013: ranking_score is an ephemeral extra column on live products
        assert set(PRODUCTS_COLUMNS).issubset(products.columns)
        assert transactions.columns == list(TRANSACTIONS_COLUMNS)
        assert products[COL_LISTING_ID].equals(products[COL_SELLER_ID])

        if transactions.height > 0:
            assert transactions[COL_TICK_ID].unique().to_list() == [tick_id]
            assert transactions[COL_PRICE_PAID].max() <= buyers["budget"].max()
            total_transactions += transactions.height

        joined = products.join(
            sellers.select([COL_SELLER_ID, COL_MARGIN_FLOOR]),
            on=COL_SELLER_ID,
            how="left",
        )
        p_min = joined.select(
            min_price_from_margin(pl.col(COL_UNIT_COST), pl.col(COL_MARGIN_FLOOR)).alias(
                "p_min"
            )
        )["p_min"]
        assert (products[COL_PRICE] >= p_min).all()

    assert total_transactions > 0
