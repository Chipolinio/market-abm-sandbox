# Назначение файла: RED-тесты слайса 5.1 — build_repricing_feature_matrix из AnalyticsStore.
# Базовая идея: проверить схему/порядок колонок, отсутствие lookahead, LOO-конкурента O(N),
# бюджет SQL (<=3) и cold-start fallback без NaN/null (Spec 005 §4.2, §5.1, §5.3.1).
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import polars as pl
import pytest

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_CAPITAL,
    COL_DELIVERY_DAYS,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_RATING_VALUE,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PRODUCTS_COLUMNS,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)

# --- SUT (ещё не существует → RED на импорте) ---
from market_abm.analytics.features import (
    MAX_SQL_ROUND_TRIPS,
    build_repricing_feature_matrix,
)
from market_abm.config.ml_repricing import CatBoostRepricingConfig, FeatureSpec

# Контракт порядка колонок (Spec 005 §5.1.3): [ключи] + [фичи по декларации §4.2].
EXPECTED_COLUMNS: list[str] = [
    "listing_id",
    "seller_id",
    "strategy_type",
    "price",
    "unit_cost",
    "demand_index",
    "margin_floor",
    "capital",
    "lag_gmv_seller_1",
    "lag_tx_count_seller_1",
    "roll_mean_price_listing_5",
    "roll_tx_count_listing_5",
    "market_mean_price_lag_1",
    "competitor_mean_price_lag_1",
    "competitor_price_gap",
    "competitor_price_change_flag",
    "ticks_since_own_price_change",
    "tick_id",
]
FEATURE_NAMES: list[str] = EXPECTED_COLUMNS[3:]  # 15 фич без 3 ключей
KEY_COLUMNS: list[str] = EXPECTED_COLUMNS[:3]
INT_COLUMNS = {"listing_id", "seller_id", "tick_id"}
# Фичи, которые на cold-start падают в текущую цену (§5.1.4 price-level зона).
PRICE_LEVEL_FALLBACK = {
    "roll_mean_price_listing_5",
    "market_mean_price_lag_1",
    "competitor_mean_price_lag_1",
}
# Фичи, которые на cold-start падают в fill_null (0.0): count/flag/gap/counter.
ZERO_FALLBACK = {
    "lag_gmv_seller_1",
    "lag_tx_count_seller_1",
    "roll_tx_count_listing_5",
    "competitor_price_gap",
    "competitor_price_change_flag",
    "ticks_since_own_price_change",
}


# --- Фикстуры/билдеры (паттерн tests/analytics/test_analytics_store.py) ---


def _run_config(tmp_path: Path, *, run_id: str) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id=run_id
        ),
    )


def _sellers_df(
    seller_ids: list[int],
    strategies: list[str],
    *,
    margin_floor: float = 0.1,
    capital: float = 1000.0,
) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: strategies,
            COL_CAPITAL: [capital] * n,
            COL_MARGIN_FLOOR: [margin_floor] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col(COL_CAPITAL).cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    ).select(list(SELLERS_COLUMNS))


def _listings_df(
    listing_ids: list[int],
    seller_ids: list[int],
    prices: list[float],
    *,
    unit_cost: float = 20.0,
    demand: float = 1.0,
) -> pl.DataFrame:
    n = len(listing_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [unit_cost] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [demand] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    ).select(list(LISTINGS_COLUMNS))


def _products(
    listing_ids: list[int],
    seller_ids: list[int],
    prices: list[float],
    *,
    unit_cost: float = 20.0,
    demand: float = 1.0,
) -> pl.DataFrame:
    n = len(listing_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [unit_cost] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [demand] * n,
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
    ).select(list(PRODUCTS_COLUMNS))


def _empty_tx() -> pl.DataFrame:
    schema = {name: getattr(pl, dt) for name, dt in TRANSACTIONS_SCHEMA_DTYPES.items()}
    return pl.DataFrame({col: [] for col in TRANSACTIONS_COLUMNS}, schema=schema)


def _persist_run(
    tmp_path: Path,
    *,
    run_id: str,
    products_by_tick: list[pl.DataFrame],
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
) -> Path:
    config = _run_config(tmp_path, run_id=run_id)
    buyers = pl.DataFrame({COL_BUYER_ID: [0]}).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32)
    )
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers,
        sellers_df=sellers_df,
        listings_df=listings_df,
        n_ticks=len(products_by_tick),
    )
    con = open_duckdb_connection(config.persistence)
    try:
        for tick_id, products in enumerate(products_by_tick):
            persist_tick_artifacts(
                ctx.run_root,
                tick_id=tick_id,
                transactions_df=_empty_tx(),
                products_df=products,
                config=config.persistence,
                con=con,
            )
    finally:
        con.close()
    return ctx.run_root


# --- 5.1-T1 ---


def test_feature_matrix_schema_and_height(tmp_path: Path) -> None:
    listing_ids = [0, 1]
    seller_ids = [0, 1]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume"])
    listings = _listings_df(listing_ids, seller_ids, [100.0, 200.0])
    products = [
        _products(listing_ids, seller_ids, [100.0, 200.0]),
        _products(listing_ids, seller_ids, [102.0, 198.0]),
        _products(listing_ids, seller_ids, [101.0, 205.0]),
    ]
    run_root = _persist_run(
        tmp_path,
        run_id="t1-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    spec = FeatureSpec.v1_default()
    config = CatBoostRepricingConfig()
    store = AnalyticsStore(run_root)
    try:
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=2,
            listings_df=listings,
            sellers_df=sellers,
            spec=spec,
            config=config,
        )
    finally:
        store.close()

    assert out.columns == EXPECTED_COLUMNS
    assert out.height == listings.height
    assert list(spec.feature_names) == FEATURE_NAMES
    for col in INT_COLUMNS:
        assert out.schema[col] == pl.Int32
    for col in FEATURE_NAMES:
        if col == "tick_id":
            continue
        assert out.schema[col] in (pl.Float32, pl.Float64)


# --- 5.1-T2 ---


def test_feature_matrix_sorted_listing_id(tmp_path: Path) -> None:
    listing_ids = [3, 1, 2, 0]
    seller_ids = [3, 1, 2, 0]
    sellers = _sellers_df(
        seller_ids, ["MaxProfit", "MaxVolume", "RatingMaximizer", "MaxProfit"]
    )
    listings = _listings_df(listing_ids, seller_ids, [80.0, 90.0, 70.0, 60.0])
    products = [
        _products([0, 1, 2, 3], [0, 1, 2, 3], [60.0, 90.0, 70.0, 80.0]),
        _products([0, 1, 2, 3], [0, 1, 2, 3], [61.0, 92.0, 71.0, 79.0]),
    ]
    run_root = _persist_run(
        tmp_path,
        run_id="t2-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    try:
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=2,
            listings_df=listings,
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
        )
    finally:
        store.close()

    ids = out[COL_LISTING_ID].to_list()
    assert ids == sorted(ids)
    assert out[COL_LISTING_ID].n_unique() == out.height


# --- 5.1-T3 (cold-start fallback, §5.1.4) ---


def test_cold_start_fallback_at_tick_zero(tmp_path: Path) -> None:
    listing_ids = [0, 1]
    seller_ids = [0, 1]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume"])
    cur_prices = [100.0, 250.0]
    listings = _listings_df(listing_ids, seller_ids, cur_prices)
    products = [_products(listing_ids, seller_ids, cur_prices)]
    run_root = _persist_run(
        tmp_path,
        run_id="t3-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    try:
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=0,
            listings_df=listings,
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
        )
    finally:
        store.close()

    # Запрет NaN/null во всех колонках (§5.1.4).
    nulls = out.null_count().row(0)
    assert sum(nulls) == 0
    for col in FEATURE_NAMES:
        if out.schema[col] in (pl.Float32, pl.Float64):
            assert not out[col].is_nan().any()

    by_listing = {row[COL_LISTING_ID]: row for row in out.iter_rows(named=True)}
    price_by_listing = dict(zip(listing_ids, cur_prices))
    for lid, row in by_listing.items():
        for col in ZERO_FALLBACK:
            assert row[col] == pytest.approx(0.0)
        for col in PRICE_LEVEL_FALLBACK:
            assert row[col] == pytest.approx(price_by_listing[lid])


# --- 5.1-T4 (no lookahead) ---


def test_no_lookahead_truncated_run(tmp_path: Path) -> None:
    listing_ids = [0, 1]
    seller_ids = [0, 1]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume"])
    listings = _listings_df(listing_ids, seller_ids, [120.0, 220.0])
    full_prices = [
        [100.0, 200.0],
        [110.0, 210.0],
        [115.0, 205.0],
        [130.0, 230.0],
        [140.0, 250.0],
    ]
    full_products = [_products(listing_ids, seller_ids, p) for p in full_prices]
    trunc_products = full_products[:3]  # только tick_id < 3

    full_root = _persist_run(
        tmp_path,
        run_id="t4-full",
        products_by_tick=full_products,
        sellers_df=sellers,
        listings_df=listings,
    )
    trunc_root = _persist_run(
        tmp_path,
        run_id="t4-trunc",
        products_by_tick=trunc_products,
        sellers_df=sellers,
        listings_df=listings,
    )

    spec = FeatureSpec.v1_default()
    config = CatBoostRepricingConfig()
    full_store = AnalyticsStore(full_root)
    trunc_store = AnalyticsStore(trunc_root)
    try:
        full_feats = build_repricing_feature_matrix(
            full_store,
            as_of_tick=3,
            listings_df=listings,
            sellers_df=sellers,
            spec=spec,
            config=config,
        )
        trunc_feats = build_repricing_feature_matrix(
            trunc_store,
            as_of_tick=3,
            listings_df=listings,
            sellers_df=sellers,
            spec=spec,
            config=config,
        )
    finally:
        full_store.close()
        trunc_store.close()

    def _norm(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(pl.col(COL_STRATEGY_TYPE).cast(pl.String))

    assert _norm(full_feats).equals(_norm(trunc_feats))


# --- 5.1-T5 (market lag uses only past) ---


def test_market_lag_uses_price_index_only_past(tmp_path: Path) -> None:
    listing_ids = [0, 1]
    seller_ids = [0, 1]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume"])
    listings = _listings_df(listing_ids, seller_ids, [300.0, 400.0])
    prices = [
        [100.0, 200.0],  # tick 0 mean 150
        [120.0, 220.0],  # tick 1 mean 170
        [140.0, 260.0],  # tick 2 mean 200
        [500.0, 900.0],  # tick 3 (>= as_of, не должен учитываться)
    ]
    products = [_products(listing_ids, seller_ids, p) for p in prices]
    run_root = _persist_run(
        tmp_path,
        run_id="t5-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    try:
        ref = store.price_index_by_tick()
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=3,
            listings_df=listings,
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
        )
    finally:
        store.close()

    expected_lag = ref.filter(pl.col(COL_TICK_ID) == 2)["mean_price"][0]
    for val in out["market_mean_price_lag_1"].to_list():
        assert val == pytest.approx(expected_lag, abs=1e-4)


# --- 5.1-T6 (SQL budget <= 3) ---


def test_feature_build_sql_round_trips_bounded(tmp_path: Path) -> None:
    n = 200
    listing_ids = list(range(n))
    seller_ids = list(range(n))
    strategies = [("MaxProfit", "MaxVolume")[i % 2] for i in range(n)]
    sellers = _sellers_df(seller_ids, strategies)
    base_prices = [50.0 + i for i in range(n)]
    listings = _listings_df(listing_ids, seller_ids, base_prices)
    products = [
        _products(listing_ids, seller_ids, [p + t for p in base_prices])
        for t in range(3)
    ]
    run_root = _persist_run(
        tmp_path,
        run_id="t6-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    calls = {"n": 0}
    original = store._query_pl

    def _spy(sql: str, params: list[object]) -> pl.DataFrame:
        calls["n"] += 1
        return original(sql, params)

    try:
        with patch.object(store, "_query_pl", side_effect=_spy):
            build_repricing_feature_matrix(
                store,
                as_of_tick=3,
                listings_df=listings,
                sellers_df=sellers,
                spec=FeatureSpec.v1_default(),
                config=CatBoostRepricingConfig(),
            )
    finally:
        store.close()

    assert calls["n"] <= MAX_SQL_ROUND_TRIPS


# --- 5.1-T7 (competitor features present) ---


def test_competitor_features_present(tmp_path: Path) -> None:
    listing_ids = [0, 1]
    seller_ids = [0, 1]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume"])
    listings = _listings_df(listing_ids, seller_ids, [100.0, 200.0])
    products = [
        _products(listing_ids, seller_ids, [100.0, 200.0]),
        _products(listing_ids, seller_ids, [101.0, 199.0]),
    ]
    run_root = _persist_run(
        tmp_path,
        run_id="t7-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    try:
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=2,
            listings_df=listings,
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
        )
    finally:
        store.close()

    required = {
        "competitor_mean_price_lag_1",
        "competitor_price_gap",
        "competitor_price_change_flag",
        "ticks_since_own_price_change",
    }
    assert required.issubset(set(out.columns))


# --- 5.1-T8 (LOO competitor matches O(N) reference) ---


def test_competitor_mean_loo_matches_reference(tmp_path: Path) -> None:
    n_listings = 500
    n_ticks = 10
    rng = np.random.default_rng(7)
    listing_ids = list(range(n_listings))
    seller_ids = list(range(n_listings))
    sellers = _sellers_df(
        seller_ids,
        [("MaxProfit", "MaxVolume")[i % 2] for i in range(n_listings)],
    )
    products = []
    for t in range(n_ticks):
        prices = (50.0 + rng.uniform(0.0, 100.0, size=n_listings)).round(4).tolist()
        products.append(_products(listing_ids, seller_ids, prices))
    listings = _listings_df(
        listing_ids, seller_ids, [80.0] * n_listings
    )
    run_root = _persist_run(
        tmp_path,
        run_id="t8-run",
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    try:
        hist = store.avg_price_by_listing_over_time()
        out = build_repricing_feature_matrix(
            store,
            as_of_tick=n_ticks,
            listings_df=listings,
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
        )
    finally:
        store.close()

    lag_tick = n_ticks - 1
    sub = hist.filter(pl.col(COL_TICK_ID) == lag_tick)
    g_sum = float(sub[COL_PRICE].sum())
    g_cnt = sub.height
    ref = sub.with_columns(
        ((g_sum - pl.col(COL_PRICE)) / (g_cnt - 1)).alias("loo")
    )
    ref_by_listing = {
        row[COL_LISTING_ID]: row["loo"] for row in ref.iter_rows(named=True)
    }

    out_by_listing = {
        row[COL_LISTING_ID]: row["competitor_mean_price_lag_1"]
        for row in out.iter_rows(named=True)
    }
    assert set(out_by_listing) == set(ref_by_listing)
    ref_vec = np.array([ref_by_listing[i] for i in listing_ids])
    out_vec = np.array([out_by_listing[i] for i in listing_ids])
    assert np.allclose(out_vec, ref_vec, atol=1e-6)
