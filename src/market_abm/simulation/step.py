# Назначение файла: один шаг симуляции рынка (выбор покупателей, сделки, репрайс).
# Базовая идея: чистая функция step(...) возвращает новые products и transactions.
from __future__ import annotations

import numpy as np
import polars as pl

from market_abm.config.shocks import ShockCatalogConfig
from market_abm.config.simulation import SimulationStepConfig
from market_abm.domain.constants import (
    BUYERS_COLUMNS,
    COL_BUYER_ID,
    COL_DEMAND_INDEX,
    COL_DELIVERY_DAYS,
    COL_GROSS_MARGIN,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_TICK_ID,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PRODUCTS_COLUMNS,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)
from typing import TYPE_CHECKING

from market_abm.analytics.features import build_repricing_feature_matrix
from market_abm.analytics.store import AnalyticsStore
from market_abm.simulation.choice import choose_listings_for_all_buyers
from market_abm.simulation.repricing import apply_ml_repricing_tick, apply_repricing_tick
from market_abm.simulation.seller_economics import (
    filter_bankrupt_listings,
    settle_seller_economics,
)
from market_abm.simulation.shocks import apply_environment_shocks

if TYPE_CHECKING:  # только типы: избегаем цикла ml.__init__ → bootstrap → runner → step
    from market_abm.ml.catboost_repricing import CatBoostModelRegistry
    from market_abm.simulation.context import SimulationContext

# Соль потока exploration для детерминизма rng в ML-репрайсе (Spec 005 §4.5).
_EXPLORE_SALT = 0xE5910E


def _step_rng(config: SimulationStepConfig) -> np.random.Generator:
    """Считает seed шага из config.seed и tick_id."""
    base = 0 if config.seed is None else config.seed
    sub = int(np.random.SeedSequence([base, config.tick_id]).generate_state(1)[0])
    return np.random.default_rng(sub)


def _validate_buyers_df(buyers_df: pl.DataFrame) -> None:
    missing = [c for c in BUYERS_COLUMNS if c not in buyers_df.columns]
    if missing:
        raise ValueError(f"buyers_df is missing required columns: {missing}")


def _validate_sellers_df(sellers_df: pl.DataFrame) -> None:
    missing = [c for c in SELLERS_COLUMNS if c not in sellers_df.columns]
    if missing:
        raise ValueError(f"sellers_df is missing required columns: {missing}")


def _validate_products_df(products_df: pl.DataFrame) -> None:
    missing = [c for c in PRODUCTS_COLUMNS if c not in products_df.columns]
    if missing:
        raise ValueError(f"products_df is missing required columns: {missing}")


def _empty_transactions_df() -> pl.DataFrame:
    """Возвращает пустую transactions_df с нужной схемой."""
    schema = {name: getattr(pl, dtype_name) for name, dtype_name in TRANSACTIONS_SCHEMA_DTYPES.items()}
    return pl.DataFrame({col: [] for col in TRANSACTIONS_COLUMNS}, schema=schema)


def _select_active_buyers(buyers_df: pl.DataFrame, rng: np.random.Generator) -> pl.DataFrame:
    """Оставляет покупателей, которые заходят на рынок в этом тике."""
    freq = buyers_df[COL_PURCHASE_FREQUENCY].to_numpy()
    active_mask = rng.random(freq.shape[0]) < freq
    return buyers_df.filter(pl.Series(active_mask))


def _build_transactions_df(
    choices_df: pl.DataFrame,
    products_df: pl.DataFrame,
    *,
    tick_id: int,
) -> pl.DataFrame:
    """Собирает transactions_df только из успешных покупок."""
    purchases = choices_df.filter(pl.col(COL_LISTING_ID).is_not_null())
    if purchases.height == 0:
        return _empty_transactions_df()

    product_fields = products_df.select(
        [COL_LISTING_ID, COL_SELLER_ID, COL_PRICE, COL_UNIT_COST]
    )
    joined = purchases.join(product_fields, on=COL_LISTING_ID, how="left")
    return joined.with_columns(
        pl.lit(tick_id, dtype=pl.Int32).alias(COL_TICK_ID),
        pl.col(COL_PRICE).alias(COL_PRICE_PAID),
        (pl.col(COL_PRICE) - pl.col(COL_UNIT_COST)).alias(COL_GROSS_MARGIN),
    ).select(list(TRANSACTIONS_COLUMNS))


def _update_demand_index(
    products_df: pl.DataFrame,
    transactions_df: pl.DataFrame,
    *,
    active_buyers_count: int,
) -> pl.DataFrame:
    """Пересчитывает demand_index по формуле из spec 003 §4.2."""
    listings_count = products_df.height
    if listings_count == 0:
        return products_df

    expected = active_buyers_count / listings_count
    if transactions_df.height == 0:
        sales = pl.DataFrame(
            {COL_LISTING_ID: [], "sales_count": []},
            schema={COL_LISTING_ID: pl.Int32, "sales_count": pl.UInt32},
        )
    else:
        sales = transactions_df.group_by(COL_LISTING_ID).len().rename({"len": "sales_count"})

    demand = (
        products_df.select(COL_LISTING_ID)
        .join(sales, on=COL_LISTING_ID, how="left")
        .with_columns(pl.col("sales_count").fill_null(0))
        .with_columns(
            pl.when(pl.lit(expected) > 0.0)
            .then(pl.col("sales_count").cast(pl.Float32) / pl.lit(expected, dtype=pl.Float32))
            .otherwise(pl.lit(0.0, dtype=pl.Float32))
            .alias(COL_DEMAND_INDEX)
        )
        .select([COL_LISTING_ID, COL_DEMAND_INDEX])
    )
    return (
        products_df.drop(COL_DEMAND_INDEX)
        .join(demand, on=COL_LISTING_ID, how="left")
        .select(list(PRODUCTS_COLUMNS))
    )


def _ml_explore_rng(config: SimulationStepConfig) -> np.random.Generator:
    """Детерминированный rng для exploration: SeedSequence(seed, tick_id, salt) (Spec 005 §4.5)."""
    base = 0 if config.seed is None else config.seed
    seq = np.random.SeedSequence([base, config.tick_id, _EXPLORE_SALT])
    return np.random.default_rng(seq)


def _use_ml_path(
    config: SimulationStepConfig,
    ml_registry: CatBoostModelRegistry | None,
) -> bool:
    """ML-ветка активна для mode catboost/hybrid после warmup при наличии registry (§9.1)."""
    repricing = config.repricing
    if repricing.mode not in ("catboost", "hybrid"):
        return False
    if config.tick_id < repricing.warmup_ticks:
        return False
    return ml_registry is not None


def _ml_reprice(
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    ml_registry: CatBoostModelRegistry,
    analytics_store: AnalyticsStore,
) -> pl.DataFrame:
    """Один ML-репрайс-тик: features (as_of=tick) → predict_next_prices → apply_ml_repricing_tick."""
    from market_abm.ml.catboost_repricing import predict_next_prices

    ml_config = config.repricing.ml
    listings_sorted = listings_df.sort(COL_LISTING_ID)
    features = build_repricing_feature_matrix(
        analytics_store,
        as_of_tick=config.tick_id,
        listings_df=listings_sorted,
        sellers_df=sellers_df,
        spec=ml_config.feature_spec,
        config=ml_config,
    )
    current_prices = features[COL_PRICE].to_numpy().astype(np.float32)
    next_prices = predict_next_prices(
        ml_registry,
        features,
        current_prices=current_prices,
        config=ml_config,
        rng=_ml_explore_rng(config),
    )
    return apply_ml_repricing_tick(
        sellers_df,
        listings_sorted,
        next_prices=next_prices,
        tick=config.tick_id,
        config=config.repricing,
    )


def _reprice_to_products(
    sellers_df: pl.DataFrame,
    products_with_demand: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    ml_registry: CatBoostModelRegistry | None,
    analytics_store: AnalyticsStore | None,
) -> pl.DataFrame:
    """Выбирает rules/ML-путь репрайса и пришивает карточные фичи обратно в products."""
    listings = products_with_demand.select(list(LISTINGS_COLUMNS))
    if _use_ml_path(config, ml_registry):
        if analytics_store is None:
            raise ValueError(
                "analytics_store is required for ML repricing (mode="
                f"{config.repricing.mode!r}, tick={config.tick_id})"
            )
        repriced = _ml_reprice(
            sellers_df,
            listings,
            config,
            ml_registry=ml_registry,
            analytics_store=analytics_store,
        )
    else:
        repriced = apply_repricing_tick(
            sellers_df, listings, tick=config.tick_id, config=config.repricing
        )
    card_features = products_with_demand.select(
        [COL_LISTING_ID, COL_DELIVERY_DAYS, COL_RATING_VALUE]
    )
    return repriced.join(card_features, on=COL_LISTING_ID, how="left").select(
        list(PRODUCTS_COLUMNS)
    )


def _settle_if_needed(
    sellers_state_df: pl.DataFrame | None,
    transactions_df: pl.DataFrame,
    config: SimulationStepConfig,
) -> pl.DataFrame | None:
    if sellers_state_df is None:
        return None
    return settle_seller_economics(
        sellers_state_df,
        transactions_df,
        config.economics,
    )


def step(
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    sellers_state_df: pl.DataFrame | None = None,
    simulation_context: SimulationContext | None = None,
    shock_catalog: ShockCatalogConfig | None = None,
    ml_registry: CatBoostModelRegistry | None = None,
    analytics_store: AnalyticsStore | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame | None]:
    """
    Выполняет один тик: шоки → filter bankrupt → choice → transactions → settle.
    sellers_state_next — None если sellers_state_df не передан (backward compat).
    """
    _validate_buyers_df(buyers_df)
    _validate_sellers_df(sellers_df)
    _validate_products_df(products_df)

    catalog = shock_catalog or ShockCatalogConfig()
    buyers_work, products_work = apply_environment_shocks(
        buyers_df,
        products_df,
        simulation_context,
        catalog,
    )
    products_pool = filter_bankrupt_listings(products_work, sellers_state_df)

    if products_pool.height == 0:
        empty_tx = _empty_transactions_df()
        return products_pool.clone(), empty_tx, _settle_if_needed(
            sellers_state_df, empty_tx, config
        )

    rng = _step_rng(config)
    active_buyers = _select_active_buyers(buyers_work, rng)
    if active_buyers.height == 0:
        empty_tx = _empty_transactions_df()
        products_with_demand = _update_demand_index(
            products_pool.clone(),
            empty_tx,
            active_buyers_count=0,
        )
        products_next = _reprice_to_products(
            sellers_df,
            products_with_demand,
            config,
            ml_registry=ml_registry,
            analytics_store=analytics_store,
        )
        return products_next, empty_tx, _settle_if_needed(
            sellers_state_df, empty_tx, config
        )

    choices = choose_listings_for_all_buyers(
        active_buyers,
        products_pool,
        seed=config.seed,
        config=config.choice,
    )
    transactions = _build_transactions_df(
        choices, products_pool, tick_id=config.tick_id
    )
    products_with_demand = _update_demand_index(
        products_pool.clone(),
        transactions,
        active_buyers_count=active_buyers.height,
    )
    products_next = _reprice_to_products(
        sellers_df,
        products_with_demand,
        config,
        ml_registry=ml_registry,
        analytics_store=analytics_store,
    )
    return (
        products_next,
        transactions,
        _settle_if_needed(sellers_state_df, transactions, config),
    )
