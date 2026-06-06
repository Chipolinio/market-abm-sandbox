# Назначение файла: extended run_simulation — sellers_state, persist (Slice 8.4).
from __future__ import annotations

from pathlib import Path

import polars as pl

from market_abm.analytics.persist import open_duckdb_connection
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.config.repricing import RepricingConfig
from market_abm.domain.constants import COL_IS_BANKRUPT, COL_SELLER_ID, COL_WORKING_CAPITAL
from market_abm.simulation.runner import run_simulation_and_persist
from tests.simulation.test_runner import _buyers_df, _listings_df, _run_config, _sellers_df


def test_run_simulation_extended_persists_sellers_state(tmp_path: Path) -> None:
    config = _run_config(seed=3).model_copy(
        update={
            "runtime_mode": "extended",
            "persistence": PersistenceConfig(
                enabled=True, base_dir=str(tmp_path), run_id="ext-run"
            ),
        }
    )
    buyers = _buyers_df(30, freq=1.0)
    sellers = _sellers_df(4)
    listings = _listings_df(4)

    gen = run_simulation_and_persist(
        buyers, sellers, listings, n_ticks=2, config=config
    )
    list(gen)

    run_root = tmp_path / "ext-run"
    state_path = run_root / "sellers_state" / "tick_000000.parquet"
    assert state_path.is_file()
    state_df = pl.read_parquet(state_path)
    assert COL_WORKING_CAPITAL in state_df.columns
    assert COL_IS_BANKRUPT in state_df.columns
    assert state_df.height == sellers.height


def test_run_simulation_extended_cumulative_gmv_in_ticker(tmp_path: Path) -> None:
    config = _run_config(seed=5).model_copy(
        update={
            "runtime_mode": "extended",
            "choice": ChoiceModelConfig(
                engine="numpy_softmax",
                max_products_per_choice_set=20,
                buyers_batch_size=200,
                outside_utility_bias=-50.0,
            ),
            "persistence": PersistenceConfig(
                enabled=True, base_dir=str(tmp_path), run_id="gmv-run"
            ),
        }
    )
    buyers = _buyers_df(40, freq=1.0)
    sellers = _sellers_df(3)
    listings = _listings_df(3)

    gen = run_simulation_and_persist(
        buyers, sellers, listings, n_ticks=3, config=config
    )
    ticks = list(gen)
    assert len(ticks) == 3

    run_root = tmp_path / "gmv-run"
    store = AnalyticsStore(run_root)
    try:
        from market_abm.analytics.ticker import query_ticker_metrics

        metrics = query_ticker_metrics(store, tick_id=2)
    finally:
        store.close()

    assert metrics["total_market_gmv"] > 0.0
    assert metrics["current_tick"] == 2
