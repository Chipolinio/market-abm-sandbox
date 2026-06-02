# Назначение файла: bootstrap-сбор обучающей выборки CatBoost из persisted-истории (Spec 005 §6).
# Базовая идея: для t в 0..T-2 — features(as_of=t) (слайс 5.1) + label log(p_{t+1}/p_t); фильтр
# RatingMaximizer, дедуп (run_id, tick_id, listing_id), gate min_rows_per_strategy. Без RAM-лога.
from __future__ import annotations

from pathlib import Path
from typing import Final

import polars as pl

from market_abm.analytics.features import build_repricing_feature_matrix
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.ml_repricing import (
    BootstrapConfig,
    CatBoostRepricingConfig,
    FeatureSpec,
)
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_PRICE,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_UNIT_COST,
)
from market_abm.simulation.runner import run_simulation_and_persist

LABEL_COLUMN: Final[str] = "label_log_price_delta"
_RATING_MAXIMIZER: Final[str] = "RatingMaximizer"
_DEDUP_KEYS: Final[list[str]] = ["run_id", COL_TICK_ID, COL_LISTING_ID]


def collect_bootstrap_training_frame(
    run_roots: list[Path],
    *,
    sellers_df: pl.DataFrame,
    spec: FeatureSpec,
    config: CatBoostRepricingConfig,
    min_rows_per_strategy: int = 0,
) -> pl.DataFrame:
    """
    Собирает обучающий frame из 1+ persisted run (Spec 005 §6.2).

    Колонки: run_id + 18 фич-колонок (слайс 5.1) + label_log_price_delta.
    Инварианты: нет строк RatingMaximizer; ключ (run_id, tick_id, listing_id) уникален;
    при min_rows_per_strategy > 0 каждая стратегия config.strategies должна иметь >= порога строк.
    """
    frames: list[pl.DataFrame] = []
    for run_root in run_roots:
        store = AnalyticsStore(Path(run_root))
        try:
            run_frame = _training_rows_for_run(
                store,
                run_root=Path(run_root),
                sellers_df=sellers_df,
                spec=spec,
                config=config,
            )
        finally:
            store.close()
        if run_frame is not None and run_frame.height > 0:
            frames.append(run_frame)

    if not frames:
        return _empty_training_frame(spec)

    training = pl.concat(frames, how="vertical_relaxed")
    training = training.filter(
        pl.col(COL_STRATEGY_TYPE).cast(pl.String) != _RATING_MAXIMIZER
    )
    training = training.unique(subset=_DEDUP_KEYS, keep="first").sort(_DEDUP_KEYS)

    if min_rows_per_strategy > 0:
        _enforce_min_rows(training, config.strategies, min_rows_per_strategy)

    return training


def run_bootstrap_simulation(
    config: BootstrapConfig,
    *,
    base_dir: Path,
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
) -> list[Path]:
    """N независимых rule-based прогонов с persistence; возвращает список run_root (Spec 005 §6.2)."""
    run_roots: list[Path] = []
    for i in range(config.n_runs):
        run_id = f"{config.run_id_prefix}-{i}"
        run_config = SimulationRunConfig(
            seed=config.population_seed + i,
            choice=ChoiceModelConfig(
                engine="numpy_softmax", outside_utility_bias=-100.0
            ),
            repricing=RepricingConfig.default_market(),
            persistence=PersistenceConfig(
                enabled=True, base_dir=str(base_dir), run_id=run_id
            ),
        )
        gen = run_simulation_and_persist(
            buyers_df,
            sellers_df,
            listings_df,
            n_ticks=config.n_ticks_per_run,
            config=run_config,
        )
        for _tick in gen:
            pass
        run_roots.append(Path(base_dir) / run_id)
    return run_roots


# --- Внутренние помощники ---


def _training_rows_for_run(
    store: AnalyticsStore,
    *,
    run_root: Path,
    sellers_df: pl.DataFrame,
    spec: FeatureSpec,
    config: CatBoostRepricingConfig,
) -> pl.DataFrame | None:
    run_id = run_root.name
    index = store.price_index_by_tick()
    if index.height == 0:
        return None
    t_max = int(index[COL_TICK_ID].max())

    rows: list[pl.DataFrame] = []
    for t in range(t_max):  # t in 0..t_max-1, чтобы snapshot t+1 существовал
        snap_t = store.products_snapshot_at_tick(t)
        snap_next = store.products_snapshot_at_tick(t + 1)
        if snap_t.height == 0 or snap_next.height == 0:
            continue

        op_listings = _snapshot_to_listings(snap_t)
        feats = build_repricing_feature_matrix(
            store,
            as_of_tick=t,
            listings_df=op_listings,
            sellers_df=sellers_df,
            spec=spec,
            config=config,
        )
        label = _label_rows(snap_t, snap_next)
        row = (
            feats.join(label, on=COL_LISTING_ID, how="inner")
            .with_columns(pl.lit(run_id).alias("run_id"))
            .select(["run_id", *feats.columns, LABEL_COLUMN])
        )
        if row.height > 0:
            rows.append(row)

    if not rows:
        return None
    return pl.concat(rows, how="vertical_relaxed")


def _snapshot_to_listings(snapshot: pl.DataFrame) -> pl.DataFrame:
    return snapshot.select(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )


def _label_rows(snap_t: pl.DataFrame, snap_next: pl.DataFrame) -> pl.DataFrame:
    price_t = snap_t.select(
        COL_LISTING_ID, pl.col(COL_PRICE).cast(pl.Float64).alias("_price_t")
    )
    price_next = snap_next.select(
        COL_LISTING_ID, pl.col(COL_PRICE).cast(pl.Float64).alias("_price_next")
    )
    return (
        price_t.join(price_next, on=COL_LISTING_ID, how="inner")
        .with_columns(
            (pl.col("_price_next") / pl.col("_price_t")).log().alias(LABEL_COLUMN)
        )
        .select(COL_LISTING_ID, LABEL_COLUMN)
    )


def _enforce_min_rows(
    training: pl.DataFrame, strategies: tuple[str, ...], min_rows: int
) -> None:
    counts = (
        training.group_by(pl.col(COL_STRATEGY_TYPE).cast(pl.String).alias("_strategy"))
        .len()
    )
    by_strategy = {row["_strategy"]: row["len"] for row in counts.iter_rows(named=True)}
    for strategy in strategies:
        found = by_strategy.get(strategy, 0)
        if found < min_rows:
            raise ValueError(
                f"insufficient bootstrap rows for strategy {strategy}: "
                f"{found} < {min_rows}"
            )


def _empty_training_frame(spec: FeatureSpec) -> pl.DataFrame:
    columns = [
        "run_id",
        COL_LISTING_ID,
        COL_SELLER_ID,
        COL_STRATEGY_TYPE,
        *spec.feature_names,
        LABEL_COLUMN,
    ]
    return pl.DataFrame({name: [] for name in columns})
