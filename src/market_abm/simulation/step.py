# Назначение файла: один шаг симуляции рынка (выбор покупателей, сделки, репрайс).
# Базовая идея: чистая функция step(...) возвращает новые products и transactions.
from __future__ import annotations

import time

import numpy as np
import polars as pl

from market_abm.config.macro import MacroDynamicsConfig
from market_abm.config.ml_runtime import MlRuntimeConfig
from market_abm.config.shocks import ShockCatalogConfig
from market_abm.config.simulation import SimulationStepConfig
from market_abm.domain.constants import (
    BUYERS_COLUMNS,
    COL_BUYER_ID,
    COL_CATEGORY_ID,
    COL_DEMAND_INDEX,
    COL_DELIVERY_DAYS,
    COL_FREQ_EFFECTIVE,
    COL_GROSS_MARGIN,
    COL_INBOUND_ETA_TICKS,
    COL_INBOUND_UNIT_COST,
    COL_INBOUND_UNITS,
    COL_IS_CHURNED,
    COL_LISTING_ID,
    COL_PRICE,
    COL_PRICE_PAID,
    COL_PURCHASE_FREQUENCY,
    COL_RANKING_SCORE,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_STOCK_TARGET,
    COL_STOCK_UNITS,
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
from market_abm.simulation.buyers_baseline import ensure_budget_baseline, ensure_buyer_economic_columns
from market_abm.simulation.choice import choose_listings_for_all_buyers
from market_abm.simulation.context import SimulationContext
from market_abm.simulation.inventory import (
    advance_replenishment,
    apply_stock_sales,
    clip_choices_to_stock,
    compute_holding_by_seller,
    filter_in_stock,
)
from market_abm.simulation.ranking import compute_ranking_scores
from market_abm.simulation.rating import update_rating_ema
from market_abm.simulation.ref_price import (
    DEFAULT_SALES_WINDOW_TICKS,
    advance_realism_windows,
    aggregate_sales_volume_by_listing,
    resolve_reference_price,
)
from market_abm.simulation.repricing import (
    apply_ml_repricing_tick,
    apply_repricing_tick,
    build_stress_repricing_profile,
)
from market_abm.simulation.seller_economics import (
    filter_bankrupt_listings,
    settle_seller_economics,
)
from market_abm.simulation.shocks import (
    COL_PROMOTION_ANCHOR,
    apply_environment_shocks,
    apply_marketplace_promotion_caps,
    drop_promotion_columns,
)

if TYPE_CHECKING:  # только типы: избегаем цикла ml.__init__ → bootstrap → runner → step
    from market_abm.ml.catboost_repricing import CatBoostModelRegistry

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
    """Оставляет некоторых покупателей по freq_effective; churned исключаются."""
    active = buyers_df.filter(~pl.col(COL_IS_CHURNED))
    if active.height == 0:
        return active
    freq = active[COL_FREQ_EFFECTIVE].to_numpy()
    active_mask = rng.random(freq.shape[0]) < freq
    return active.filter(pl.Series(active_mask))


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
    # Preserve extra columns (e.g. category_id) not in PRODUCTS_COLUMNS contract (Spec 012 §7.1)
    extra_cols = [c for c in products_df.columns if c not in set(PRODUCTS_COLUMNS)]
    out_cols = list(PRODUCTS_COLUMNS) + extra_cols
    return (
        products_df.drop(COL_DEMAND_INDEX)
        .join(demand, on=COL_LISTING_ID, how="left")
        .select(out_cols)
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
    ml_runtime: MlRuntimeConfig | None = None,
) -> pl.DataFrame | None:
    """
    ML-репрайс-тик с бюджетом inference (Spec 011 §5A.3).
    None → caller falls back to rules path.
    """
    from market_abm.ml.catboost_repricing import predict_next_prices

    runtime = ml_runtime or MlRuntimeConfig()
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
    if features.height > runtime.max_listings_per_ml_tick:
        return None

    current_prices = features[COL_PRICE].to_numpy().astype(np.float32)
    started = time.perf_counter()
    next_prices = predict_next_prices(
        ml_registry,
        features,
        current_prices=current_prices,
        config=ml_config,
        rng=_ml_explore_rng(config),
        min_listing_price=config.repricing.min_listing_price,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    if elapsed_ms > runtime.inference_timeout_ms and runtime.fallback_to_rules_on_timeout:
        return None

    return apply_ml_repricing_tick(
        sellers_df,
        listings_sorted,
        next_prices=next_prices,
        tick=config.tick_id,
        config=config.repricing,
    )


def _rules_repricing(
    sellers_df: pl.DataFrame,
    listings: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    simulation_context: SimulationContext | None,
) -> pl.DataFrame:
    if config.tick_id < config.repricing.warmup_ticks:
        return listings
    profile = None
    if simulation_context is not None:
        profile = build_stress_repricing_profile(
            simulation_context.macro,
            config.repricing,
        )
    return apply_repricing_tick(
        sellers_df,
        listings,
        tick=config.tick_id,
        config=config.repricing,
        repricing_profile=profile,
        inventory_pricing=config.inventory_pricing,
    )


def _reprice_to_products(
    sellers_df: pl.DataFrame,
    products_with_demand: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    ml_registry: CatBoostModelRegistry | None,
    analytics_store: AnalyticsStore | None,
    simulation_context: SimulationContext | None = None,
    shock_catalog: ShockCatalogConfig | None = None,
    ml_runtime: MlRuntimeConfig | None = None,
) -> pl.DataFrame:
    """Выбирает rules/ML-путь репрайса и пришивает карточные фичи обратно в products."""
    catalog = shock_catalog or ShockCatalogConfig()
    listing_cols = list(LISTINGS_COLUMNS)
    # Preserve category_id for competitor repricing and ranking (Spec 012 §4.3 / §7.1)
    if COL_CATEGORY_ID in products_with_demand.columns:
        listing_cols = [*listing_cols, COL_CATEGORY_ID]
    # Spec 012.1: stock / inbound cols needed for inventory pressure + survive reprice
    for stock_col in (
        COL_STOCK_UNITS,
        COL_STOCK_TARGET,
        COL_INBOUND_UNITS,
        COL_INBOUND_ETA_TICKS,
        COL_INBOUND_UNIT_COST,
    ):
        if stock_col in products_with_demand.columns:
            listing_cols = [*listing_cols, stock_col]
    if COL_PROMOTION_ANCHOR in products_with_demand.columns:
        listing_cols = [*listing_cols, COL_PROMOTION_ANCHOR]
    listings = products_with_demand.select(listing_cols)
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
            ml_runtime=ml_runtime,
        )
        if repriced is None:
            repriced = _rules_repricing(
                sellers_df,
                listings,
                config,
                simulation_context=simulation_context,
            )
    else:
        repriced = _rules_repricing(
            sellers_df,
            listings,
            config,
            simulation_context=simulation_context,
        )
    card_features = products_with_demand.select(
        [COL_LISTING_ID, COL_DELIVERY_DAYS, COL_RATING_VALUE]
    )
    merged = repriced.join(card_features, on=COL_LISTING_ID, how="left")
    if COL_PROMOTION_ANCHOR in products_with_demand.columns and COL_PROMOTION_ANCHOR not in merged.columns:
        merged = merged.join(
            products_with_demand.select([COL_LISTING_ID, COL_PROMOTION_ANCHOR]),
            on=COL_LISTING_ID,
            how="left",
        )
    # Spec 013: ranking_score; Spec 012.1: stock_* / inbound_* — survive reprice join
    for extra_col in (
        COL_RANKING_SCORE,
        COL_STOCK_UNITS,
        COL_STOCK_TARGET,
        COL_INBOUND_UNITS,
        COL_INBOUND_ETA_TICKS,
        COL_INBOUND_UNIT_COST,
    ):
        if extra_col in products_with_demand.columns and extra_col not in merged.columns:
            merged = merged.join(
                products_with_demand.select([COL_LISTING_ID, extra_col]),
                on=COL_LISTING_ID,
                how="left",
            )
    merged = apply_marketplace_promotion_caps(merged, simulation_context, catalog)
    # Preserve extra columns (category_id, ranking_score, etc.) (Spec 012 §7.1 / Spec 013)
    select_cols = list(PRODUCTS_COLUMNS)
    extra_from_products = [
        c for c in products_with_demand.columns
        if c not in set(PRODUCTS_COLUMNS) and c != COL_PROMOTION_ANCHOR
        and c in merged.columns
    ]
    select_cols = select_cols + extra_from_products
    if COL_PROMOTION_ANCHOR in merged.columns:
        select_cols = [*select_cols, COL_PROMOTION_ANCHOR]
    return merged.select(select_cols)


def _settle_if_needed(
    sellers_state_df: pl.DataFrame | None,
    transactions_df: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    products_df: pl.DataFrame | None = None,
) -> pl.DataFrame | None:
    if sellers_state_df is None:
        return None
    prepaid = bool(config.replenishment.enabled)
    holding = None
    if prepaid and products_df is not None and COL_STOCK_UNITS in products_df.columns:
        holding = compute_holding_by_seller(
            products_df,
            holding_cost_per_unit_tick=config.replenishment.holding_cost_per_unit_tick,
        )
    return settle_seller_economics(
        sellers_state_df,
        transactions_df,
        config.economics,
        prepaid_cogs=prepaid,
        holding_by_seller=holding,
    )


def _replenish_if_needed(
    products_df: pl.DataFrame,
    sellers_state_df: pl.DataFrame | None,
    config: SimulationStepConfig,
) -> tuple[pl.DataFrame, pl.DataFrame | None]:
    """Spec 012.1 §6: ETA / arrive / reorder after sales."""
    if not config.replenishment.enabled or sellers_state_df is None:
        return products_df, sellers_state_df
    if COL_STOCK_UNITS not in products_df.columns:
        return products_df, sellers_state_df
    return advance_replenishment(products_df, sellers_state_df, config.replenishment)


def step(
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    products_df: pl.DataFrame,
    config: SimulationStepConfig,
    *,
    sellers_state_df: pl.DataFrame | None = None,
    simulation_context: SimulationContext | None = None,
    shock_catalog: ShockCatalogConfig | None = None,
    macro_config: MacroDynamicsConfig | None = None,
    ml_registry: CatBoostModelRegistry | None = None,
    analytics_store: AnalyticsStore | None = None,
    ml_runtime: MlRuntimeConfig | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame | None, SimulationContext | None]:
    """
    Выполняет один тик: шоки → filter bankrupt → ranking → ref → choice → tx → windows.
    Возвращает (products, transactions, sellers_state_next, simulation_context_next).
    sellers_state_next — None если sellers_state_df не передан (backward compat).
    simulation_context_next — advanced windows если ctx передан, иначе None.
    """
    buyers_df = ensure_buyer_economic_columns(ensure_budget_baseline(buyers_df))
    _validate_buyers_df(buyers_df)
    _validate_sellers_df(sellers_df)
    _validate_products_df(products_df)

    catalog = shock_catalog or ShockCatalogConfig()
    buyers_work, products_work = apply_environment_shocks(
        buyers_df,
        products_df,
        simulation_context,
        catalog,
        macro_config=macro_config,
    )
    products_available = filter_bankrupt_listings(products_work, sellers_state_df)

    # Spec 012.1 §4.4: OOS filter BEFORE ranking / consideration
    if config.inventory.enabled:
        products_pool = filter_in_stock(products_available)
    else:
        products_pool = products_available

    if products_pool.height == 0:
        empty_tx = _empty_transactions_df()
        ledger = products_available if products_available.height > 0 else products_pool
        ledger, sellers_state_df = _replenish_if_needed(ledger, sellers_state_df, config)
        products_with_demand = _update_demand_index(
            ledger.clone(),
            empty_tx,
            active_buyers_count=0,
        )
        products_next = _reprice_to_products(
            sellers_df,
            products_with_demand,
            config,
            ml_registry=ml_registry,
            analytics_store=analytics_store,
            simulation_context=simulation_context,
            shock_catalog=catalog,
            ml_runtime=ml_runtime,
        )
        products_next = drop_promotion_columns(products_next)
        return (
            products_next,
            empty_tx,
            _settle_if_needed(
                sellers_state_df, empty_tx, config, products_df=products_next
            ),
            simulation_context,
        )

    rng = _step_rng(config)
    active_buyers = _select_active_buyers(buyers_work, rng)
    if active_buyers.height == 0:
        empty_tx = _empty_transactions_df()
        ledger = products_available.clone() if config.inventory.enabled else products_pool.clone()
        ledger, sellers_state_df = _replenish_if_needed(ledger, sellers_state_df, config)
        products_with_demand = _update_demand_index(
            ledger,
            empty_tx,
            active_buyers_count=0,
        )
        products_next = _reprice_to_products(
            sellers_df,
            products_with_demand,
            config,
            ml_registry=ml_registry,
            analytics_store=analytics_store,
            simulation_context=simulation_context,
            shock_catalog=catalog,
            ml_runtime=ml_runtime,
        )
        ctx_next = simulation_context
        if ctx_next is not None:
            ctx_next = advance_realism_windows(
                ctx_next,
                empty_tx,
                products_pool,
                ref_cfg=config.choice.reference_price,
                sales_window_ticks=DEFAULT_SALES_WINDOW_TICKS,
            )
        products_next = drop_promotion_columns(products_next)
        return (
            products_next,
            empty_tx,
            _settle_if_needed(
                sellers_state_df, empty_tx, config, products_df=products_next
            ),
            ctx_next,
        )

    # Spec 013 §4: one ranking precompute/tick → consideration Top-K ∪ Sample-M
    sales_from_ctx = (
        aggregate_sales_volume_by_listing(simulation_context)
        if simulation_context is not None
        else None
    )
    ranked = compute_ranking_scores(
        products_pool,
        config.choice.ranking,
        sales_volume_by_listing=sales_from_ctx,
    )
    ranking_scores = ranked[COL_RANKING_SCORE].to_numpy()
    if COL_CATEGORY_ID in ranked.columns:
        category_ids = ranked[COL_CATEGORY_ID].to_numpy()
    else:
        # Spec 013 §4.3 / §17#5: rating-only scores; still activate consideration path
        category_ids = np.zeros(ranked.height, dtype=np.int32)

    # Spec 013 §5: resolve rolling / cold-start reference price
    ref_price = resolve_reference_price(
        simulation_context,
        ranked,
        config.choice.reference_price,
    )

    choices = choose_listings_for_all_buyers(
        active_buyers,
        ranked,
        seed=config.seed,
        config=config.choice,
        segment_elasticity=(
            macro_config.segment_elasticity if macro_config is not None else None
        ),
        ref_price=ref_price,
        category_ids=category_ids,
        ranking_scores=ranking_scores,
    )
    # Spec 012.1 §17 #2 A: clip purchases to available stock (buyer_id order)
    if config.inventory.enabled:
        choices = clip_choices_to_stock(choices, products_pool)

    transactions = _build_transactions_df(
        choices, ranked, tick_id=config.tick_id
    )

    ctx_next = simulation_context
    if ctx_next is not None:
        ctx_next = advance_realism_windows(
            ctx_next,
            transactions,
            ranked,
            ref_cfg=config.choice.reference_price,
            sales_window_ticks=DEFAULT_SALES_WINDOW_TICKS,
        )

    # Spec 012.1 §4.3: decrement stock on full available ledger (incl. unchanged OOS rows)
    if config.inventory.enabled:
        ledger = apply_stock_sales(products_available, transactions)
        if COL_RANKING_SCORE in ranked.columns:
            ledger = ledger.join(
                ranked.select([COL_LISTING_ID, COL_RANKING_SCORE]),
                on=COL_LISTING_ID,
                how="left",
            )
    else:
        ledger = ranked

    # Spec 012.1 §6: ETA / arrive / reorder (prepaid capital) after sales
    ledger, sellers_state_df = _replenish_if_needed(ledger, sellers_state_df, config)

    # Spec 012 §6: EMA rating update from seed-aware reviews after settle
    products_rated = update_rating_ema(
        ledger,
        transactions,
        seed=config.seed,
        tick_id=config.tick_id,
        cfg=config.rating,
    )
    products_with_demand = _update_demand_index(
        products_rated,
        transactions,
        active_buyers_count=active_buyers.height,
    )
    products_next = _reprice_to_products(
        sellers_df,
        products_with_demand,
        config,
        ml_registry=ml_registry,
        analytics_store=analytics_store,
        simulation_context=simulation_context,
        shock_catalog=catalog,
        ml_runtime=ml_runtime,
    )
    products_next = drop_promotion_columns(products_next)
    return (
        products_next,
        transactions,
        _settle_if_needed(
            sellers_state_df, transactions, config, products_df=products_next
        ),
        ctx_next,
    )
