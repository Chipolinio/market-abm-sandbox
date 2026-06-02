# Назначение файла: RED-тесты слайса 5.5 — интеграция ML-репрайсинга в step (Spec 005 §8.2, §9, §12.6).
# Базовая идея: step ветвится по repricing.mode + warmup_ticks; ML-путь меняет цены (vs rules),
# warmup → rules, mode=rules игнорирует ml-аргументы, ML без store → ValueError, p_min держится.
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl
import pytest

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.ml_repricing import CatBoostRepricingConfig, V1_FEATURE_NAMES
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
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
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PLATFORM_DEFAULTS,
    PRODUCTS_COLUMNS,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)
from market_abm.ml.catboost_repricing import CatBoostModelRegistry
from market_abm.simulation.step import step

pytestmark = pytest.mark.ml

_UNIT_COST = 20.0
_MARGIN_FLOOR = 0.1
_TOTAL_FEES = PLATFORM_DEFAULTS["base_commission"] + PLATFORM_DEFAULTS["logistic_fee"]
_P_MIN = _UNIT_COST / (1.0 - _MARGIN_FLOOR - _TOTAL_FEES)


# --- Поддельная модель CatBoost: константная log-дельта (без обучения) ---


class _FakeModel:
    def __init__(self, y_value: float) -> None:
        self.y_value = y_value

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(x).shape[0], self.y_value, dtype=np.float64)


def _fake_registry(y_value: float) -> CatBoostModelRegistry:
    return CatBoostModelRegistry(
        models={"MaxProfit": _FakeModel(y_value), "MaxVolume": _FakeModel(y_value)},
        feature_names=V1_FEATURE_NAMES,
        train_config_hash="sha256:test",
    )


# --- Фикстуры данных (паттерн _persist_run из 5.2) ---


def _sellers_df(seller_ids: list[int], strategies: list[str]) -> pl.DataFrame:
    n = len(seller_ids)
    return (
        pl.DataFrame(
            {
                COL_SELLER_ID: seller_ids,
                COL_STRATEGY_TYPE: strategies,
                COL_CAPITAL: [1000.0] * n,
                COL_MARGIN_FLOOR: [_MARGIN_FLOOR] * n,
                COL_REPRICING_SPEED: [1] * n,
            }
        )
        .with_columns(
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
            pl.col(COL_CAPITAL).cast(pl.Float32),
            pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
            pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
        )
        .select(list(SELLERS_COLUMNS))
    )


def _listings_df(
    listing_ids: list[int], seller_ids: list[int], prices: list[float]
) -> pl.DataFrame:
    n = len(listing_ids)
    return (
        pl.DataFrame(
            {
                COL_LISTING_ID: listing_ids,
                COL_SELLER_ID: seller_ids,
                COL_UNIT_COST: [_UNIT_COST] * n,
                COL_PRICE: prices,
                COL_DEMAND_INDEX: [1.0] * n,
            }
        )
        .with_columns(
            pl.col(COL_LISTING_ID).cast(pl.Int32),
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_UNIT_COST).cast(pl.Float32),
            pl.col(COL_PRICE).cast(pl.Float32),
            pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        )
        .select(list(LISTINGS_COLUMNS))
    )


def _products(
    listing_ids: list[int], seller_ids: list[int], prices: list[float]
) -> pl.DataFrame:
    n = len(listing_ids)
    return (
        pl.DataFrame(
            {
                COL_LISTING_ID: listing_ids,
                COL_SELLER_ID: seller_ids,
                COL_UNIT_COST: [_UNIT_COST] * n,
                COL_PRICE: prices,
                COL_DEMAND_INDEX: [1.0] * n,
                COL_DELIVERY_DAYS: [3.0] * n,
                COL_RATING_VALUE: [4.0] * n,
            }
        )
        .with_columns(
            pl.col(COL_LISTING_ID).cast(pl.Int32),
            pl.col(COL_SELLER_ID).cast(pl.Int32),
            pl.col(COL_UNIT_COST).cast(pl.Float32),
            pl.col(COL_PRICE).cast(pl.Float32),
            pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
            pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
            pl.col(COL_RATING_VALUE).cast(pl.Float32),
        )
        .select(list(PRODUCTS_COLUMNS))
    )


def _buyers_df() -> pl.DataFrame:
    # purchase_frequency = 0 → нет активных покупателей, детерминированно (репрайс всё равно идёт).
    n = 2
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            "budget": [500.0] * n,
            "beta_price": [-0.2] * n,
            "beta_delivery": [-0.3] * n,
            "beta_rating": [-0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            "purchase_frequency": [0.0] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col("budget").cast(pl.Float32),
        pl.col("beta_price").cast(pl.Float32),
        pl.col("beta_delivery").cast(pl.Float32),
        pl.col("beta_rating").cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col("purchase_frequency").cast(pl.Float32),
    )


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
    config = SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id),
    )
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


def _setup(
    tmp_path: Path, run_id: str
) -> tuple[AnalyticsStore, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    listing_ids = [0, 1, 2]
    seller_ids = [0, 1, 2]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume", "RatingMaximizer"])
    listings = _listings_df(listing_ids, seller_ids, [100.0, 200.0, 150.0])
    products_by_tick = [
        _products(listing_ids, seller_ids, [100.0 + t, 200.0 + 2 * t, 150.0 + t])
        for t in range(12)
    ]
    run_root = _persist_run(
        tmp_path,
        run_id=run_id,
        products_by_tick=products_by_tick,
        sellers_df=sellers,
        listings_df=listings,
    )
    store = AnalyticsStore(run_root)
    buyers = _buyers_df()
    products_op = _products(listing_ids, seller_ids, [110.0, 210.0, 160.0])
    return store, buyers, sellers, products_op


def _ml_config(*, tick_id: int, warmup_ticks: int) -> SimulationStepConfig:
    return SimulationStepConfig(
        tick_id=tick_id,
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig(
            mode="catboost", warmup_ticks=warmup_ticks, ml=CatBoostRepricingConfig()
        ),
    )


def _rules_config(*, tick_id: int) -> SimulationStepConfig:
    return SimulationStepConfig(
        tick_id=tick_id,
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
    )


def _price_by_listing(products_df: pl.DataFrame) -> dict[int, float]:
    return {row[COL_LISTING_ID]: row[COL_PRICE] for row in products_df.iter_rows(named=True)}


# --- 5.5-T1 ---


def test_step_ml_mode_changes_price(tmp_path: Path) -> None:
    store, buyers, sellers, products = _setup(tmp_path, "ml-t1")
    try:
        prod_ml, _ = step(
            buyers,
            sellers,
            products,
            _ml_config(tick_id=10, warmup_ticks=5),
            ml_registry=_fake_registry(0.1),
            analytics_store=store,
        )
    finally:
        store.close()
    prod_rules, _ = step(buyers, sellers, products, _rules_config(tick_id=10))

    ml_prices = _price_by_listing(prod_ml)
    rules_prices = _price_by_listing(prod_rules)
    # ML-стратегии (0 MaxProfit, 1 MaxVolume) расходятся с rule-путём
    assert ml_prices[0] != pytest.approx(rules_prices[0])
    assert ml_prices[1] != pytest.approx(rules_prices[1])
    # RatingMaximizer (2) — no-op, остаётся на операционной цене
    assert ml_prices[2] == pytest.approx(160.0, abs=1e-3)


# --- 5.5-T2 ---


def test_step_warmup_uses_rules(tmp_path: Path) -> None:
    store, buyers, sellers, products = _setup(tmp_path, "ml-t2")
    try:
        prod_ml, _ = step(
            buyers,
            sellers,
            products,
            _ml_config(tick_id=2, warmup_ticks=5),  # tick < warmup → rules
            ml_registry=_fake_registry(0.5),
            analytics_store=store,
        )
    finally:
        store.close()
    prod_rules, _ = step(buyers, sellers, products, _rules_config(tick_id=2))

    assert _price_by_listing(prod_ml) == pytest.approx(_price_by_listing(prod_rules))


# --- 5.5-T3 ---


def test_step_rules_mode_unchanged_regression(tmp_path: Path) -> None:
    store, buyers, sellers, products = _setup(tmp_path, "ml-t3")
    config = _rules_config(tick_id=10)
    try:
        prod_plain, _ = step(buyers, sellers, products, config)
        prod_with_ml_args, _ = step(
            buyers,
            sellers,
            products,
            config,
            ml_registry=_fake_registry(0.5),
            analytics_store=store,
        )
    finally:
        store.close()
    # mode=rules игнорирует ml-аргументы
    assert _price_by_listing(prod_plain) == pytest.approx(
        _price_by_listing(prod_with_ml_args)
    )


# --- 5.5-T4 ---


def test_step_ml_without_store_raises(tmp_path: Path) -> None:
    store, buyers, sellers, products = _setup(tmp_path, "ml-t4")
    store.close()
    with pytest.raises(ValueError):
        step(
            buyers,
            sellers,
            products,
            _ml_config(tick_id=10, warmup_ticks=5),
            ml_registry=_fake_registry(0.1),
            analytics_store=None,
        )


# --- 5.5-T5 ---


def test_p_min_still_enforced(tmp_path: Path) -> None:
    store, buyers, sellers, products = _setup(tmp_path, "ml-t5")
    try:
        prod_ml, _ = step(
            buyers,
            sellers,
            products,
            _ml_config(tick_id=10, warmup_ticks=5),
            ml_registry=_fake_registry(-10.0),  # exp(-10) → price-crash, должен сработать p_min
            analytics_store=store,
        )
    finally:
        store.close()
    prices = _price_by_listing(prod_ml)
    assert prices[0] >= _P_MIN - 1e-2  # MaxProfit
    assert prices[1] >= _P_MIN - 1e-2  # MaxVolume
