# Назначение файла: CQRS query-side — сборка матрицы признаков репрайсинга из AnalyticsStore.
# Базовая идея: <=3 SQL round-trips, competitor LOO O(N) = (sum-own)/(cnt-1), cold-start fallback
# без NaN/null; вся деривация фич — векторно в Polars (Spec 005 §4.2, §5.1, §5.3.1).
from __future__ import annotations

from typing import Final

import polars as pl

from market_abm.analytics.store import AnalyticsStore
from market_abm.config.ml_repricing import CatBoostRepricingConfig, FeatureSpec
from market_abm.domain.constants import (
    COL_CAPITAL,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
)

# Жёсткий бюджет SQL на один вызов build_repricing_feature_matrix (Spec 005 §5.3 SQL-1).
MAX_SQL_ROUND_TRIPS: Final[int] = 3

_TICK_ID_FROM_FILENAME: Final = (
    "CAST(regexp_extract(filename, 'tick_([0-9]+)', 1) AS INTEGER)"
)

# Колонки выхода: [ключи] + [фичи по декларации] (Spec 005 §5.1.3).
_KEY_COLUMNS: Final[tuple[str, ...]] = (COL_LISTING_ID, COL_SELLER_ID, COL_STRATEGY_TYPE)

# Фичи price-level: на cold-start падают в текущую цену (Spec 005 §5.1.4).
_PRICE_LEVEL_FEATURES: Final[tuple[str, ...]] = (
    "roll_mean_price_listing_5",
    "market_mean_price_lag_1",
    "competitor_mean_price_lag_1",
)


def build_repricing_feature_matrix(
    store: AnalyticsStore,
    *,
    as_of_tick: int,
    listings_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    spec: FeatureSpec,
    config: CatBoostRepricingConfig,
    lookback_ticks: int | None = None,
) -> pl.DataFrame:
    """
    Собирает features_df для всех listing_id из listings_df (Spec 005 §5.1).

    Инварианты:
    - height == listings_df.height, listing_id уникален и отсортирован по возрастанию;
    - ни одна агрегация не использует tick_id >= as_of_tick (нет lookahead);
    - cold-start: price-level фичи → текущая цена, count/flag → fill_null, без NaN/null;
    - порядок колонок == [ключи] + spec.feature_names.
    """
    if as_of_tick < 0:
        raise ValueError(f"as_of_tick must be >= 0, got {as_of_tick}")

    lookback = lookback_ticks if lookback_ticks is not None else spec.lookback_ticks
    lag_tick = as_of_tick - 1
    window_lo = as_of_tick - lookback

    base = listings_df.join(
        sellers_df.select(
            [COL_SELLER_ID, COL_STRATEGY_TYPE, COL_MARGIN_FLOOR, COL_CAPITAL]
        ),
        on=COL_SELLER_ID,
        how="left",
    )

    hist = _read_products_history(store, as_of_tick)
    tx = _read_transactions_history(store, as_of_tick)

    market = (
        hist.group_by(COL_TICK_ID)
        .agg(
            pl.col(COL_PRICE).sum().alias("sum_price"),
            pl.len().alias("cnt"),
            pl.col(COL_PRICE).mean().alias("mean_price"),
        )
        if hist.height > 0
        else pl.DataFrame(
            schema={
                COL_TICK_ID: pl.Int32,
                "sum_price": pl.Float64,
                "cnt": pl.UInt32,
                "mean_price": pl.Float64,
            }
        )
    )
    mean_lag = _scalar_at_tick(market, lag_tick, "mean_price")
    mean_lag_prev = _scalar_at_tick(market, lag_tick - 1, "mean_price")
    sum_lag = _scalar_at_tick(market, lag_tick, "sum_price")
    cnt_lag = _scalar_at_tick(market, lag_tick, "cnt")

    change_flag = (
        1.0
        if mean_lag is not None
        and mean_lag_prev is not None
        and abs(mean_lag - mean_lag_prev) > config.competitor_change_eps
        else 0.0
    )

    competitor = _competitor_mean_at_lag(hist, lag_tick, sum_lag, cnt_lag)
    rolling = _rolling_price(hist, window_lo, lag_tick)
    ticks_since = _ticks_since_change(hist, lag_tick, config.price_change_eps, lookback)
    seller_lag = _seller_lag(tx, lag_tick)
    listing_roll_tx = _listing_roll_tx(tx, window_lo, lag_tick)

    feats = (
        base.join(competitor, on=COL_LISTING_ID, how="left")
        .join(rolling, on=COL_LISTING_ID, how="left")
        .join(ticks_since, on=COL_LISTING_ID, how="left")
        .join(seller_lag, on=COL_SELLER_ID, how="left")
        .join(listing_roll_tx, on=COL_LISTING_ID, how="left")
    )

    market_lag_expr = (
        pl.lit(float(mean_lag)).cast(pl.Float64)
        if mean_lag is not None
        else pl.col(COL_PRICE).cast(pl.Float64)
    )

    feats = feats.with_columns(
        market_lag_expr.alias("market_mean_price_lag_1"),
        pl.lit(change_flag, dtype=pl.Float32).alias("competitor_price_change_flag"),
        pl.lit(as_of_tick, dtype=pl.Int32).alias(COL_TICK_ID),
    )

    # Cold-start fallback (§5.1.4): price-level → текущая цена; count/flag/counter → fill_null.
    price_f64 = pl.col(COL_PRICE).cast(pl.Float64)
    feats = feats.with_columns(
        pl.col("competitor_mean_price_lag_1").fill_null(price_f64),
        pl.col("roll_mean_price_listing_5").fill_null(price_f64),
        pl.col("market_mean_price_lag_1").fill_null(price_f64),
        pl.col("lag_gmv_seller_1").fill_null(spec.fill_null).cast(pl.Float64),
        pl.col("lag_tx_count_seller_1").fill_null(spec.fill_null).cast(pl.Float64),
        pl.col("roll_tx_count_listing_5").fill_null(spec.fill_null).cast(pl.Float64),
        pl.col("ticks_since_own_price_change")
        .fill_null(spec.fill_null)
        .cast(pl.Float32),
    )
    feats = feats.with_columns(
        (pl.col("competitor_mean_price_lag_1") - price_f64)
        .cast(pl.Float64)
        .alias("competitor_price_gap")
    )

    ordered = [*_KEY_COLUMNS, *spec.feature_names]
    return feats.select(ordered).sort(COL_LISTING_ID)


# --- SQL чтение истории (round-trips через store._query_pl) ---


def _read_products_history(store: AnalyticsStore, as_of_tick: int) -> pl.DataFrame:
    """Сырая история цен products_snapshots при tick_id < as_of_tick (один scan)."""
    empty = pl.DataFrame(
        schema={COL_TICK_ID: pl.Int32, COL_LISTING_ID: pl.Int32, COL_PRICE: pl.Float64}
    )
    if not store._has_parquet_files("products_snapshots"):
        return empty
    sql = f"""
        SELECT tick_id, listing_id, price FROM (
            SELECT
                {_TICK_ID_FROM_FILENAME} AS tick_id,
                listing_id,
                price::DOUBLE AS price
            FROM read_parquet(?, filename=true)
        )
        WHERE tick_id < ?
    """
    return store._query_pl(sql, [store._products_glob(), as_of_tick])


def _read_transactions_history(store: AnalyticsStore, as_of_tick: int) -> pl.DataFrame:
    """Сырая история сделок при tick_id < as_of_tick (один scan)."""
    empty = pl.DataFrame(
        schema={
            COL_TICK_ID: pl.Int32,
            COL_SELLER_ID: pl.Int32,
            COL_LISTING_ID: pl.Int32,
            "price_paid": pl.Float64,
        }
    )
    if not store._has_parquet_files("transactions"):
        return empty
    sql = """
        SELECT tick_id, seller_id, listing_id, price_paid::DOUBLE AS price_paid
        FROM read_parquet(?)
        WHERE tick_id < ?
    """
    return store._query_pl(sql, [store._transactions_glob(), as_of_tick])


# --- Векторные деривации в Polars (без циклов по SKU) ---


def _scalar_at_tick(market: pl.DataFrame, tick: int, col: str) -> float | None:
    if market.height == 0:
        return None
    row = market.filter(pl.col(COL_TICK_ID) == tick)
    if row.height == 0:
        return None
    value = row[col][0]
    return None if value is None else float(value)


def _competitor_mean_at_lag(
    hist: pl.DataFrame,
    lag_tick: int,
    sum_lag: float | None,
    cnt_lag: float | None,
) -> pl.DataFrame:
    """LOO competitor mean = (global_sum - own_price) / (global_cnt - 1) на lag-тике (§5.3.1)."""
    schema = {COL_LISTING_ID: pl.Int32, "competitor_mean_price_lag_1": pl.Float64}
    if hist.height == 0:
        return pl.DataFrame(schema=schema)
    at_lag = hist.filter(pl.col(COL_TICK_ID) == lag_tick).select(
        [COL_LISTING_ID, COL_PRICE]
    )
    if at_lag.height == 0:
        return pl.DataFrame(schema=schema)
    if sum_lag is None or cnt_lag is None or cnt_lag <= 1:
        return at_lag.select(
            COL_LISTING_ID,
            pl.lit(None, dtype=pl.Float64).alias("competitor_mean_price_lag_1"),
        )
    return at_lag.select(
        COL_LISTING_ID,
        ((sum_lag - pl.col(COL_PRICE)) / (cnt_lag - 1.0))
        .cast(pl.Float64)
        .alias("competitor_mean_price_lag_1"),
    )


def _rolling_price(hist: pl.DataFrame, window_lo: int, lag_tick: int) -> pl.DataFrame:
    schema = {COL_LISTING_ID: pl.Int32, "roll_mean_price_listing_5": pl.Float64}
    if hist.height == 0:
        return pl.DataFrame(schema=schema)
    return (
        hist.filter(
            (pl.col(COL_TICK_ID) >= window_lo) & (pl.col(COL_TICK_ID) <= lag_tick)
        )
        .group_by(COL_LISTING_ID)
        .agg(pl.col(COL_PRICE).mean().cast(pl.Float64).alias("roll_mean_price_listing_5"))
    )


def _ticks_since_change(
    hist: pl.DataFrame, lag_tick: int, price_eps: float, lookback: int
) -> pl.DataFrame:
    """Число тиков с последнего значимого |Δ price| (cap lookback), векторно по partition."""
    schema = {COL_LISTING_ID: pl.Int32, "ticks_since_own_price_change": pl.Float64}
    if hist.height == 0:
        return pl.DataFrame(schema=schema)
    h = hist.filter(pl.col(COL_TICK_ID) <= lag_tick).sort([COL_LISTING_ID, COL_TICK_ID])
    if h.height == 0:
        return pl.DataFrame(schema=schema)
    h = h.with_columns(
        (
            (pl.col(COL_PRICE) - pl.col(COL_PRICE).shift(1).over(COL_LISTING_ID)).abs()
            > price_eps
        ).alias("changed")
    )
    changed = (
        h.filter(pl.col("changed"))
        .group_by(COL_LISTING_ID)
        .agg(pl.col(COL_TICK_ID).max().alias("last_change_tick"))
    )
    present = h.select(COL_LISTING_ID).unique()
    return (
        present.join(changed, on=COL_LISTING_ID, how="left")
        .with_columns(
            pl.when(pl.col("last_change_tick").is_null())
            .then(pl.lit(float(lookback)))
            .otherwise(
                (lag_tick - pl.col("last_change_tick"))
                .cast(pl.Float64)
                .clip(0.0, float(lookback))
            )
            .alias("ticks_since_own_price_change")
        )
        .select([COL_LISTING_ID, "ticks_since_own_price_change"])
    )


def _seller_lag(tx: pl.DataFrame, lag_tick: int) -> pl.DataFrame:
    schema = {
        COL_SELLER_ID: pl.Int32,
        "lag_gmv_seller_1": pl.Float64,
        "lag_tx_count_seller_1": pl.Float64,
    }
    if tx.height == 0:
        return pl.DataFrame(schema=schema)
    return (
        tx.filter(pl.col(COL_TICK_ID) == lag_tick)
        .group_by(COL_SELLER_ID)
        .agg(
            pl.col("price_paid").sum().cast(pl.Float64).alias("lag_gmv_seller_1"),
            pl.len().cast(pl.Float64).alias("lag_tx_count_seller_1"),
        )
    )


def _listing_roll_tx(tx: pl.DataFrame, window_lo: int, lag_tick: int) -> pl.DataFrame:
    schema = {COL_LISTING_ID: pl.Int32, "roll_tx_count_listing_5": pl.Float64}
    if tx.height == 0:
        return pl.DataFrame(schema=schema)
    return (
        tx.filter(
            (pl.col(COL_TICK_ID) >= window_lo) & (pl.col(COL_TICK_ID) <= lag_tick)
        )
        .group_by(COL_LISTING_ID)
        .agg(pl.len().cast(pl.Float64).alias("roll_tx_count_listing_5"))
    )
