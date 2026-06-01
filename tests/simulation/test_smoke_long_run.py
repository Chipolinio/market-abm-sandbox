# Назначение файла: long-run stability — 50+ тиков без роста RAM (Slice 004 §12.6).
# Базовая идея: tracemalloc на полном исчерпании генератора; persist пишет 50+50 parquet.
from __future__ import annotations

import gc
import tracemalloc
from collections.abc import Callable
from pathlib import Path

import polars as pl
import pytest

from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    COL_BETA_DELIVERY,
    COL_BETA_PRICE,
    COL_BETA_RATING,
    COL_BUDGET,
    COL_BUYER_ID,
    COL_DEMAND_INDEX,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE,
    COL_PURCHASE_FREQUENCY,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_UNIT_COST,
)
from market_abm.simulation.runner import run_simulation, run_simulation_and_persist

N_TICKS: int = 50
N_BUYERS: int = 200
N_SELLERS: int = 40
MEMORY_THRESHOLD_MB: float = 30.0
MEMORY_THRESHOLD_PERSIST_MB: float = 40.0

pytestmark = pytest.mark.slow


def _buyers_df(n: int, *, freq: float = 1.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_BUYER_ID: list(range(n)),
            COL_BUDGET: [500.0] * n,
            COL_BETA_PRICE: [-0.2] * n,
            COL_BETA_DELIVERY: [-0.3] * n,
            COL_BETA_RATING: [-0.5] * n,
            "device_type": ["android"] * n,
            "pvd_segment": ["standard"] * n,
            "activity_hour": [12] * n,
            "is_impulsive": [False] * n,
            COL_PURCHASE_FREQUENCY: [freq] * n,
        }
    ).with_columns(
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_BUDGET).cast(pl.Float32),
        pl.col(COL_BETA_PRICE).cast(pl.Float32),
        pl.col(COL_BETA_DELIVERY).cast(pl.Float32),
        pl.col(COL_BETA_RATING).cast(pl.Float32),
        pl.col("device_type").cast(pl.Categorical),
        pl.col("pvd_segment").cast(pl.Categorical),
        pl.col("activity_hour").cast(pl.UInt8),
        pl.col("is_impulsive").cast(pl.Boolean),
        pl.col(COL_PURCHASE_FREQUENCY).cast(pl.Float32),
    )


def _sellers_df(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_SELLER_ID: list(range(n)),
            COL_STRATEGY_TYPE: ["MaxProfit"] * n,
            "capital": [100.0] * n,
            COL_MARGIN_FLOOR: [0.2] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    )


def _listings_df(n: int, *, prices: float = 80.0) -> pl.DataFrame:
    return pl.DataFrame(
        {
            COL_LISTING_ID: list(range(n)),
            COL_SELLER_ID: list(range(n)),
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: [prices] * n,
            COL_DEMAND_INDEX: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    )


def _long_run_config(
    tmp_path: Path | None = None,
    *,
    persist: bool,
    run_id: str = "long-run-50",
    seed: int = 42,
) -> SimulationRunConfig:
    persistence = (
        PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id)
        if persist and tmp_path is not None
        else PersistenceConfig(enabled=False)
    )
    return SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=50,
            buyers_batch_size=500,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
        persistence=persistence,
    )


def _long_run_inputs() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    return (
        _buyers_df(N_BUYERS, freq=1.0),
        _sellers_df(N_SELLERS),
        _listings_df(N_SELLERS),
    )


def _consume_generator(gen) -> int:
    """Исчерпывает генератор без накопления yield-значений в RAM."""
    count = 0
    for _tick_id, _products, _transactions in gen:
        count += 1
    return count


def _peak_traced_memory_mb(run: Callable[[], None]) -> float:
    gc.collect()
    tracemalloc.start()
    try:
        run()
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / (1024 * 1024)


def _count_tick_parquets(directory: Path) -> int:
    return len(list(directory.glob("tick_*.parquet")))


def test_fifty_ticks_memory_bounded() -> None:
    buyers, sellers, listings = _long_run_inputs()
    config = _long_run_config(persist=False)

    def _run() -> None:
        gen = run_simulation(buyers, sellers, listings, n_ticks=N_TICKS, config=config)
        assert _consume_generator(gen) == N_TICKS

    peak_mb = _peak_traced_memory_mb(_run)
    assert peak_mb < MEMORY_THRESHOLD_MB, f"peak traced memory {peak_mb:.1f} MB"


def test_fifty_ticks_with_persist_memory_bounded(tmp_path: Path) -> None:
    buyers, sellers, listings = _long_run_inputs()
    config = _long_run_config(tmp_path, persist=True, run_id="long-run-mem")

    def _run() -> None:
        gen = run_simulation_and_persist(
            buyers, sellers, listings, n_ticks=N_TICKS, config=config
        )
        assert _consume_generator(gen) == N_TICKS

    peak_mb = _peak_traced_memory_mb(_run)
    assert peak_mb < MEMORY_THRESHOLD_PERSIST_MB, f"peak traced memory {peak_mb:.1f} MB"


def test_fifty_ticks_produces_files(tmp_path: Path) -> None:
    buyers, sellers, listings = _long_run_inputs()
    config = _long_run_config(tmp_path, persist=True, run_id="long-run-files")
    gen = run_simulation_and_persist(
        buyers, sellers, listings, n_ticks=N_TICKS, config=config
    )
    assert _consume_generator(gen) == N_TICKS

    run_root = tmp_path / "long-run-files"
    assert (run_root / "manifest.json").is_file()
    assert _count_tick_parquets(run_root / "transactions") == N_TICKS
    assert _count_tick_parquets(run_root / "products_snapshots") == N_TICKS
