# Назначение файла: stress repricing + headroom preset (Slice 11.4, Spec 011 §13.4).
from __future__ import annotations

import polars as pl
import pytest

from market_abm.config.economics import SellerEconomicsConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.domain.constants import (
    COL_DEMAND_INDEX,
    COL_GROSS_MARGIN,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    PLATFORM_DEFAULTS,
    TRANSACTIONS_COLUMNS,
)
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.repricing import (
    apply_repricing_tick,
    build_stress_repricing_profile,
    min_price_from_margin,
)
from market_abm.simulation.seller_economics import init_sellers_state, settle_seller_economics


def _stress_macro(stress: float) -> MacroState:
    return MacroState(
        stress=stress,
        regime=MacroRegime.STRESS,
        peak_stress=stress,
    )


def _sellers_df(
    seller_ids: list[int],
    strategy_types: list[str],
    *,
    margin_floors: list[float] | None = None,
    speeds: list[int] | None = None,
    capitals: list[float] | None = None,
) -> pl.DataFrame:
    n = len(seller_ids)
    if margin_floors is None:
        margin_floors = [0.2] * n
    if speeds is None:
        speeds = [1] * n
    if capitals is None:
        capitals = [500.0] * n
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: strategy_types,
            "capital": capitals,
            COL_MARGIN_FLOOR: margin_floors,
            COL_REPRICING_SPEED: speeds,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings_from_init(n_sellers: int, *, seed: int = 42) -> tuple[pl.DataFrame, pl.DataFrame]:
    sellers = generate_sellers(
        SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
    )
    cfg = RepricingConfig.market_with_headroom()
    listings = initialize_listings(
        sellers,
        ListingInitConfig.market_with_headroom(),
        seed=seed,
        min_listing_price=cfg.min_listing_price,
    )
    return sellers, listings


def test_stress_profile_increases_step() -> None:
    config = RepricingConfig.default_market()
    profile = build_stress_repricing_profile(_stress_macro(0.5), config)

    assert profile is not None
    assert profile.relative_step > config.relative_step
    assert profile.max_volume_aggression > config.max_volume_aggression
    assert profile.max_profit_demand_high < config.max_profit_demand_high
    assert profile.max_profit_demand_low > config.max_profit_demand_low

    sellers = _sellers_df([0, 1], ["MaxProfit", "MaxVolume"])
    listings = pl.DataFrame(
        {
            COL_LISTING_ID: [0, 1],
            COL_SELLER_ID: [0, 1],
            COL_UNIT_COST: [20.0, 20.0],
            COL_PRICE: [100.0, 100.0],
            COL_DEMAND_INDEX: [0.5, 0.5],
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )

    base_out = apply_repricing_tick(sellers, listings, tick=1, config=config)
    stress_out = apply_repricing_tick(
        sellers,
        listings,
        tick=1,
        config=config,
        repricing_profile=profile,
    )

    base_drop = 100.0 - float(base_out.filter(pl.col(COL_SELLER_ID) == 1)[COL_PRICE][0])
    stress_drop = 100.0 - float(stress_out.filter(pl.col(COL_SELLER_ID) == 1)[COL_PRICE][0])
    assert stress_drop > base_drop


def test_headroom_preset_median_above_floor() -> None:
    sellers, listings = _listings_from_init(500, seed=7)
    joined = listings.join(
        sellers.select([COL_SELLER_ID, COL_MARGIN_FLOOR]),
        on=COL_SELLER_ID,
        how="left",
    )
    p_min = joined.select(
        min_price_from_margin(
            pl.col(COL_UNIT_COST),
            pl.col(COL_MARGIN_FLOOR),
            min_listing_price=RepricingConfig.market_with_headroom().min_listing_price,
        ).alias("p_min")
    )["p_min"]
    ratio = joined[COL_PRICE] / p_min
    share = float((ratio >= 1.15).mean())
    median_ratio = float(ratio.median())

    assert share >= 0.80
    assert median_ratio == pytest.approx(1.15, abs=0.01)


def test_crash_lowers_p50_over_20_ticks() -> None:
    sellers, listings = _listings_from_init(200, seed=3)
    sellers = sellers.with_columns(
        pl.lit("MaxVolume").cast(pl.Categorical).alias(COL_STRATEGY_TYPE),
        pl.lit(1).cast(pl.UInt8).alias(COL_REPRICING_SPEED),
    )
    listings = listings.with_columns(pl.lit(0.30, dtype=pl.Float32).alias(COL_DEMAND_INDEX))

    config = RepricingConfig.market_with_headroom()
    profile = build_stress_repricing_profile(_stress_macro(0.85), config)
    assert profile is not None

    p50_start = float(listings[COL_PRICE].median())
    current = listings
    for tick in range(1, 21):
        current = apply_repricing_tick(
            sellers,
            current,
            tick=tick,
            config=config,
            repricing_profile=profile,
        )

    p50_end = float(current[COL_PRICE].median())
    assert p50_end < p50_start * 0.97


def test_stress_repricing_never_below_unit_cost() -> None:
    config = RepricingConfig.default_market()
    profile = build_stress_repricing_profile(_stress_macro(1.0), config)
    assert profile is not None

    n = 50
    sellers = _sellers_df(list(range(n)), ["MaxVolume"] * n)
    listings = pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [25.0] * n,
            COL_PRICE: [120.0] * n,
            COL_DEMAND_INDEX: [0.20] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )

    out = listings
    for tick in range(1, 11):
        out = apply_repricing_tick(
            sellers,
            out,
            tick=tick,
            config=config,
            repricing_profile=profile,
        )

    joined = out.join(listings.select([COL_LISTING_ID, COL_UNIT_COST]), on=COL_LISTING_ID)
    assert (joined[COL_PRICE] >= joined[COL_UNIT_COST]).all()


def test_severe_recession_bankrupt_rate_bounded() -> None:
    n = 30
    sellers = _sellers_df(
        list(range(n)),
        ["MaxVolume"] * n,
        capitals=[80.0] * n,
        speeds=[1] * n,
    )
    config = RepricingConfig.market_with_headroom()
    listings = initialize_listings(
        sellers,
        ListingInitConfig.market_with_headroom(),
        seed=99,
        min_listing_price=config.min_listing_price,
    ).with_columns(pl.lit(0.25, dtype=pl.Float32).alias(COL_DEMAND_INDEX))

    profile = build_stress_repricing_profile(_stress_macro(1.0), config)
    assert profile is not None

    economics = SellerEconomicsConfig(fixed_cost_per_tick=1.5, bankruptcy_threshold=0.0)
    sellers_state = init_sellers_state(sellers)
    current_listings = listings

    for tick in range(30):
        prices = current_listings.select([COL_LISTING_ID, COL_SELLER_ID, COL_PRICE, COL_UNIT_COST])
        transactions = prices.with_columns(
            pl.lit(tick, dtype=pl.Int32).alias(COL_TICK_ID),
            pl.lit(0, dtype=pl.Int32).alias("buyer_id"),
            pl.col(COL_PRICE).alias(COL_PRICE_PAID),
            (pl.col(COL_PRICE) - pl.col(COL_UNIT_COST)).alias(COL_GROSS_MARGIN),
        ).select(list(TRANSACTIONS_COLUMNS))

        sellers_state = settle_seller_economics(sellers_state, transactions, economics)
        current_listings = apply_repricing_tick(
            sellers,
            current_listings,
            tick=tick + 1,
            config=config,
            repricing_profile=profile,
        )

    bankrupt_rate = float(sellers_state[COL_IS_BANKRUPT].mean())
    assert bankrupt_rate <= 0.30
