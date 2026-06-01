# Назначение файла: E2E — полный прогон с persist и SQL-метрики AnalyticsStore (Slice 004 §12.7).
# Базовая идея: run_simulation_and_persist → gmv_by_tick; стабильный config_hash в manifest.
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import pytest

from market_abm.analytics.persist import init_run_directory
from market_abm.analytics.store import AnalyticsStore
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
from market_abm.simulation.runner import run_simulation_and_persist

N_TICKS_E2E: int = 8
N_BUYERS: int = 120
N_SELLERS: int = 25


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


def _e2e_run_config(tmp_path: Path, *, run_id: str, seed: int = 42) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=50,
            buyers_batch_size=500,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True,
            base_dir=str(tmp_path),
            run_id=run_id,
        ),
    )


def _read_manifest_hash(run_root: Path) -> str:
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    return str(manifest["config_hash"])


def test_full_run_query_gmv(tmp_path: Path) -> None:
    run_id = "e2e-gmv-run"
    buyers = _buyers_df(N_BUYERS, freq=1.0)
    sellers = _sellers_df(N_SELLERS)
    listings = _listings_df(N_SELLERS)
    config = _e2e_run_config(tmp_path, run_id=run_id, seed=42)

    gen = run_simulation_and_persist(
        buyers, sellers, listings, n_ticks=N_TICKS_E2E, config=config
    )
    assert len(list(gen)) == N_TICKS_E2E

    run_root = tmp_path / run_id
    store = AnalyticsStore(run_root)
    try:
        gmv_df = store.gmv_by_tick()
    finally:
        store.close()

    assert gmv_df.height > 0, "expected at least one tick with transactions"
    assert (gmv_df["gmv"] > 0).any(), "expected positive GMV on preset with outside_utility_bias=-100"


def test_manifest_config_hash_stable(tmp_path: Path) -> None:
    buyers = _buyers_df(8, freq=1.0)
    sellers = _sellers_df(3)
    listings = _listings_df(3)
    shared = SimulationRunConfig(
        seed=99,
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=10,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True,
            base_dir=str(tmp_path),
            run_id="placeholder",
        ),
    )

    config_a = shared.model_copy(
        update={"persistence": shared.persistence.model_copy(update={"run_id": "hash-run-a"})}
    )
    config_b = shared.model_copy(
        update={"persistence": shared.persistence.model_copy(update={"run_id": "hash-run-b"})}
    )

    init_run_directory(
        config_a,
        run_id="hash-run-a",
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=3,
    )
    init_run_directory(
        config_b,
        run_id="hash-run-b",
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=3,
    )

    hash_a = _read_manifest_hash(tmp_path / "hash-run-a")
    hash_b = _read_manifest_hash(tmp_path / "hash-run-b")
    assert hash_a == hash_b
    assert hash_a.startswith("sha256:")
