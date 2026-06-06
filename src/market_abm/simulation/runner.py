# Назначение файла: много-тиковый генератор симуляции рынка (Slice 004 / 8.4).
# Базовая идея: listings → products один раз, затем ленивый yield step по тикам.
from __future__ import annotations

from collections.abc import Generator
from dataclasses import replace
from typing import Final

import numpy as np
import polars as pl

from market_abm.config.runner import ProductsBootstrapConfig, SimulationRunConfig
from market_abm.config.simulation import SimulationStepConfig
from market_abm.domain.constants import (
    COL_DELIVERY_DAYS,
    COL_RATING_VALUE,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
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
from market_abm.simulation.context import with_tick_id
from market_abm.simulation.extended_runtime import (
    ExtendedSimulationState,
    init_extended_state,
    persist_extended_tick,
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
    sellers_df: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Добавляет delivery_days и rating_value; не мутирует listings_df."""
    n = listings_df.height
    if n == 0:
        schema = {
            name: getattr(pl, dtype) for name, dtype in PRODUCTS_SCHEMA_DTYPES.items()
        }
        return pl.DataFrame({col: [] for col in PRODUCTS_COLUMNS}, schema=schema)

    delivery = rng.uniform(config.delivery_days_min, config.delivery_days_max, size=n)
    ratings = rng.uniform(config.rating_min, config.rating_max, size=n).astype(np.float32)
    if sellers_df is not None and config.rating_maximizer_boost > 0.0:
        strategy_by_seller = dict(
            zip(
                sellers_df[COL_SELLER_ID].to_list(),
                sellers_df[COL_STRATEGY_TYPE].cast(pl.String).to_list(),
                strict=True,
            )
        )
        seller_ids = listings_df[COL_SELLER_ID].to_numpy()
        boost = np.array(
            [
                config.rating_maximizer_boost
                if strategy_by_seller.get(int(sid)) == "RatingMaximizer"
                else 0.0
                for sid in seller_ids
            ],
            dtype=np.float32,
        )
        ratings = np.minimum(config.rating_max, ratings + boost)

    return listings_df.with_columns(
        pl.Series(COL_DELIVERY_DAYS, delivery, dtype=pl.Float32),
        pl.Series(COL_RATING_VALUE, ratings, dtype=pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


def _maybe_rechunk_products(products_df: pl.DataFrame) -> pl.DataFrame:
    """Сжимает чанки после step, если их слишком много."""
    if products_df.n_chunks() > PRODUCTS_RECHUNK_N_CHUNKS_THRESHOLD:
        return products_df.rechunk()
    return products_df


def _is_extended(config: SimulationRunConfig) -> bool:
    return config.runtime_mode == "extended"


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
        sellers_df=sellers_df,
    )

    extended_state: ExtendedSimulationState | None = None
    if _is_extended(config):
        extended_state = init_extended_state(sellers_df)

    for tick_id in range(n_ticks):
        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=config.seed,
            choice=config.choice,
            repricing=config.repricing,
            economics=config.economics,
        )
        sim_ctx = None
        sellers_state_df = None
        if extended_state is not None:
            sim_ctx = with_tick_id(extended_state.simulation_context, tick_id)
            sellers_state_df = extended_state.sellers_state_df

        products_next, transactions_df, sellers_state_next = step(
            buyers_df,
            sellers_df,
            products_df,
            step_config,
            sellers_state_df=sellers_state_df,
            simulation_context=sim_ctx,
            shock_catalog=config.shock_catalog,
        )
        products_next = _maybe_rechunk_products(products_next)
        products_df = products_next

        if extended_state is not None and sellers_state_next is not None:
            extended_state = replace(
                extended_state,
                sellers_state_df=sellers_state_next,
                simulation_context=with_tick_id(
                    extended_state.simulation_context, tick_id + 1
                ),
            )
            from market_abm.simulation.context import tick_down_active_shocks

            extended_state = replace(
                extended_state,
                simulation_context=tick_down_active_shocks(extended_state.simulation_context),
            )

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
            if _is_extended(config):
                yield from _stream_extended_persist(
                    buyers_df,
                    sellers_df,
                    listings_df,
                    n_ticks=n_ticks,
                    config=config,
                    run_root=ctx.run_root,
                    run_id=run_id,
                    con=con,
                )
            else:
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


def _stream_extended_persist(
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    *,
    n_ticks: int,
    config: SimulationRunConfig,
    run_root,
    run_id: str,
    con,
) -> Generator[tuple[int, pl.DataFrame, pl.DataFrame], None, None]:
    _validate_listings_df(listings_df)
    rng = _bootstrap_rng(config.seed)
    products_df = _bootstrap_products_from_listings(
        listings_df,
        config=config.products_bootstrap,
        rng=rng,
        sellers_df=sellers_df,
    )
    extended_state = init_extended_state(sellers_df)

    for tick_id in range(n_ticks):
        prev_sellers_state = extended_state.sellers_state_df
        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=config.seed,
            choice=config.choice,
            repricing=config.repricing,
            economics=config.economics,
        )
        sim_ctx = with_tick_id(extended_state.simulation_context, tick_id)
        products_next, transactions_df, sellers_state_next = step(
            buyers_df,
            sellers_df,
            products_df,
            step_config,
            sellers_state_df=extended_state.sellers_state_df,
            simulation_context=sim_ctx,
            shock_catalog=config.shock_catalog,
        )
        products_next = _maybe_rechunk_products(products_next)
        products_df = products_next

        if sellers_state_next is None:
            raise RuntimeError("extended mode requires sellers_state_next from step()")

        extended_state = replace(
            extended_state,
            sellers_state_df=sellers_state_next,
            simulation_context=sim_ctx,
        )
        extended_state = persist_extended_tick(
            run_root,
            tick_id=tick_id,
            transactions_df=transactions_df,
            products_df=products_next,
            state=extended_state,
            prev_sellers_state=prev_sellers_state,
            config=config,
            con=con,
            run_id=run_id,
        )
        yield tick_id, products_next, transactions_df
