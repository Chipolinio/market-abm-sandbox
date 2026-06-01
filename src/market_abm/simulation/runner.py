# Назначение файла: много-тиковый генератор симуляции рынка (Slice 004).
# Базовая идея: listings → products один раз, затем ленивый yield step по тикам.
from __future__ import annotations

from collections.abc import Generator
from typing import Final

import numpy as np
import polars as pl

from market_abm.config.runner import ProductsBootstrapConfig, SimulationRunConfig
from market_abm.config.simulation import SimulationStepConfig
from market_abm.domain.constants import (
    COL_DELIVERY_DAYS,
    COL_RATING_VALUE,
    LISTINGS_COLUMNS,
    PRODUCTS_COLUMNS,
    PRODUCTS_SCHEMA_DTYPES,
)
from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
    resolve_run_id,
)
from market_abm.simulation.step import step

PRODUCTS_RECHUNK_N_CHUNKS_THRESHOLD: Final[int] = 16
_BOOTSTRAP_SPICE: Final[int] = 0xB0075A9


def _bootstrap_rng(seed: int | None) -> np.random.Generator:
    """Отдельный RNG для bootstrap карточки, не пересекается с seed тиков."""
    base = 0 if seed is None else seed
    sub = int(np.random.SeedSequence([base, _BOOTSTRAP_SPICE]).generate_state(1)[0])
    return np.random.default_rng(sub)


def _validate_listings_df(listings_df: pl.DataFrame) -> None:
    missing = [c for c in LISTINGS_COLUMNS if c not in listings_df.columns]
    if missing:
        raise ValueError(f"listings_df is missing required columns: {missing}")


def _bootstrap_products_from_listings(
    listings_df: pl.DataFrame,
    *,
    config: ProductsBootstrapConfig,
    rng: np.random.Generator,
) -> pl.DataFrame:
    """Добавляет delivery_days и rating_value; не мутирует listings_df."""
    n = listings_df.height
    if n == 0:
        schema = {
            name: getattr(pl, dtype) for name, dtype in PRODUCTS_SCHEMA_DTYPES.items()
        }
        return pl.DataFrame({col: [] for col in PRODUCTS_COLUMNS}, schema=schema)

    delivery = rng.uniform(config.delivery_days_min, config.delivery_days_max, size=n)
    ratings = rng.uniform(config.rating_min, config.rating_max, size=n)
    return listings_df.with_columns(
        pl.Series(COL_DELIVERY_DAYS, delivery, dtype=pl.Float32),
        pl.Series(COL_RATING_VALUE, ratings, dtype=pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


def _maybe_rechunk_products(products_df: pl.DataFrame) -> pl.DataFrame:
    """Сжимает чанки после step, если их слишком много."""
    if products_df.n_chunks() > PRODUCTS_RECHUNK_N_CHUNKS_THRESHOLD:
        return products_df.rechunk()
    return products_df


def run_simulation(
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    n_ticks: int,
    config: SimulationRunConfig,
) -> Generator[tuple[int, pl.DataFrame, pl.DataFrame], None, None]:
    """Ленивый цикл рынка: на каждый тик yield (tick_id, products_next, transactions)."""
    if n_ticks < 1:
        raise ValueError("n_ticks must be >= 1")

    _validate_listings_df(listings_df)
    rng = _bootstrap_rng(config.seed)
    products_df = _bootstrap_products_from_listings(
        listings_df,
        config=config.products_bootstrap,
        rng=rng,
    )

    for tick_id in range(n_ticks):
        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=config.seed,
            choice=config.choice,
            repricing=config.repricing,
        )
        products_next, transactions_df = step(
            buyers_df,
            sellers_df,
            products_df,
            step_config,
        )
        products_next = _maybe_rechunk_products(products_next)
        products_df = products_next
        yield tick_id, products_next, transactions_df


def run_simulation_and_persist(
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    n_ticks: int,
    config: SimulationRunConfig,
) -> Generator[tuple[int, pl.DataFrame, pl.DataFrame], None, None]:
    """
    Как run_simulation, но при persistence.enabled пишет parquet до каждого yield.
    init_run_directory выполняется при вызове функции (до первого next).
    Без итерации step не выполняется; tick_*.parquet не создаются.
    """
    if not config.persistence.enabled:
        return run_simulation(buyers_df, sellers_df, listings_df, n_ticks, config)

    if n_ticks < 1:
        raise ValueError("n_ticks must be >= 1")

    run_id = resolve_run_id(config.persistence)
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers_df,
        sellers_df=sellers_df,
        listings_df=listings_df,
        n_ticks=n_ticks,
    )
    con = open_duckdb_connection(config.persistence)

    def _stream() -> Generator[tuple[int, pl.DataFrame, pl.DataFrame], None, None]:
        try:
            for tick_id, products_next, transactions_df in run_simulation(
                buyers_df, sellers_df, listings_df, n_ticks, config
            ):
                persist_tick_artifacts(
                    ctx.run_root,
                    tick_id=tick_id,
                    transactions_df=transactions_df,
                    products_df=products_next,
                    config=config.persistence,
                    con=con,
                )
                yield tick_id, products_next, transactions_df
        finally:
            con.close()

    return _stream()
