# Назначение файла: RED-тесты слайса 5.2 — сбор обучающей выборки bootstrap (Spec 005 §6, §12.3).
# Базовая идея: features(as_of=t) + label log(p_{t+1}/p_t); фильтр RatingMaximizer; детерминизм; min_rows gate.
from __future__ import annotations

import math
from pathlib import Path

import polars as pl
import pytest

from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
)
from market_abm.config.ml_repricing import CatBoostRepricingConfig, FeatureSpec
from market_abm.config.repricing import RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.simulation import ChoiceModelConfig
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
    COL_TICK_ID,
    COL_UNIT_COST,
    LISTINGS_COLUMNS,
    PRODUCTS_COLUMNS,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
    TRANSACTIONS_SCHEMA_DTYPES,
)

# --- SUT (ещё не существует → RED на импорте) ---
from market_abm.ml.bootstrap import collect_bootstrap_training_frame
from tests.helpers.reference_snapshots import stub_buyers_df

LABEL_COL = "label_log_price_delta"


# --- Фикстуры ---


def _run_config(tmp_path: Path, *, run_id: str) -> SimulationRunConfig:
    return SimulationRunConfig(
        seed=1,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True, base_dir=str(tmp_path), run_id=run_id
        ),
    )


def _sellers_df(seller_ids: list[int], strategies: list[str]) -> pl.DataFrame:
    n = len(seller_ids)
    return pl.DataFrame(
        {
            COL_SELLER_ID: seller_ids,
            COL_STRATEGY_TYPE: strategies,
            COL_CAPITAL: [1000.0] * n,
            COL_MARGIN_FLOOR: [0.1] * n,
            COL_REPRICING_SPEED: [1] * n,
        }
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col(COL_CAPITAL).cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    ).select(list(SELLERS_COLUMNS))


def _listings_df(
    listing_ids: list[int], seller_ids: list[int], prices: list[float]
) -> pl.DataFrame:
    n = len(listing_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
    ).select(list(LISTINGS_COLUMNS))


def _products(
    listing_ids: list[int], seller_ids: list[int], prices: list[float]
) -> pl.DataFrame:
    n = len(listing_ids)
    return pl.DataFrame(
        {
            COL_LISTING_ID: listing_ids,
            COL_SELLER_ID: seller_ids,
            COL_UNIT_COST: [20.0] * n,
            COL_PRICE: prices,
            COL_DEMAND_INDEX: [1.0] * n,
            COL_DELIVERY_DAYS: [3.0] * n,
            COL_RATING_VALUE: [4.0] * n,
        }
    ).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_PRICE).cast(pl.Float32),
        pl.col(COL_DEMAND_INDEX).cast(pl.Float32),
        pl.col(COL_DELIVERY_DAYS).cast(pl.Float32),
        pl.col(COL_RATING_VALUE).cast(pl.Float32),
    ).select(list(PRODUCTS_COLUMNS))


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
    config = _run_config(tmp_path, run_id=run_id)
    buyers = stub_buyers_df([0])
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


def _mini_run(tmp_path: Path, *, run_id: str, n_ticks: int = 5) -> tuple[Path, pl.DataFrame]:
    """Mini-run: 3 продавца (MaxProfit, MaxVolume, RatingMaximizer), растущие цены."""
    listing_ids = [0, 1, 2]
    seller_ids = [0, 1, 2]
    sellers = _sellers_df(seller_ids, ["MaxProfit", "MaxVolume", "RatingMaximizer"])
    listings = _listings_df(listing_ids, seller_ids, [100.0, 200.0, 150.0])
    products = [
        _products(
            listing_ids,
            seller_ids,
            [100.0 + t, 200.0 + 2 * t, 150.0 + t],
        )
        for t in range(n_ticks)
    ]
    run_root = _persist_run(
        tmp_path,
        run_id=run_id,
        products_by_tick=products,
        sellers_df=sellers,
        listings_df=listings,
    )
    return run_root, sellers


# --- 5.2-T1 ---


def test_training_frame_has_label_column(tmp_path: Path) -> None:
    run_root, sellers = _mini_run(tmp_path, run_id="boot-t1")
    df = collect_bootstrap_training_frame(
        [run_root],
        sellers_df=sellers,
        spec=FeatureSpec.v1_default(),
        config=CatBoostRepricingConfig(),
    )
    assert LABEL_COL in df.columns
    assert df.height > 0
    labels = df[LABEL_COL].to_list()
    assert all(v is not None and math.isfinite(v) for v in labels)


# --- 5.2-T2 ---


def test_bootstrap_deterministic_row_count(tmp_path: Path) -> None:
    run_root, sellers = _mini_run(tmp_path, run_id="boot-t2")
    spec = FeatureSpec.v1_default()
    config = CatBoostRepricingConfig()
    df1 = collect_bootstrap_training_frame(
        [run_root], sellers_df=sellers, spec=spec, config=config
    )
    df2 = collect_bootstrap_training_frame(
        [run_root], sellers_df=sellers, spec=spec, config=config
    )
    assert df1.height == df2.height
    assert df1.with_columns(pl.col(COL_STRATEGY_TYPE).cast(pl.String)).equals(
        df2.with_columns(pl.col(COL_STRATEGY_TYPE).cast(pl.String))
    )


# --- 5.2-T3 ---


def test_rating_maximizer_excluded(tmp_path: Path) -> None:
    run_root, sellers = _mini_run(tmp_path, run_id="boot-t3")
    df = collect_bootstrap_training_frame(
        [run_root],
        sellers_df=sellers,
        spec=FeatureSpec.v1_default(),
        config=CatBoostRepricingConfig(),
    )
    strategies = set(df[COL_STRATEGY_TYPE].cast(pl.String).to_list())
    assert "RatingMaximizer" not in strategies
    assert strategies.issubset({"MaxProfit", "MaxVolume"})


# --- 5.2-T4 ---


def test_min_rows_per_strategy_enforced(tmp_path: Path) -> None:
    run_root, sellers = _mini_run(tmp_path, run_id="boot-t4", n_ticks=3)
    with pytest.raises(ValueError):
        collect_bootstrap_training_frame(
            [run_root],
            sellers_df=sellers,
            spec=FeatureSpec.v1_default(),
            config=CatBoostRepricingConfig(),
            min_rows_per_strategy=10_000,
        )


# --- 5.2-T5 (full bootstrap, slow + ml) ---


@pytest.mark.slow
@pytest.mark.ml
def test_full_bootstrap_simulation_slow(tmp_path: Path) -> None:
    from market_abm.config.ml_repricing import BootstrapConfig
    from market_abm.ml.bootstrap import run_bootstrap_simulation

    n_sellers = 12
    seller_ids = list(range(n_sellers))
    strategies = [("MaxProfit", "MaxVolume", "RatingMaximizer")[i % 3] for i in range(n_sellers)]
    sellers = _sellers_df(seller_ids, strategies)
    listings = _listings_df(
        seller_ids, seller_ids, [80.0 + i for i in range(n_sellers)]
    )
    buyers = pl.DataFrame(
        {
            COL_BUYER_ID: list(range(50)),
            "budget": [500.0] * 50,
            "beta_price": [-0.2] * 50,
            "beta_delivery": [-0.3] * 50,
            "beta_rating": [-0.5] * 50,
            "device_type": ["android"] * 50,
            "pvd_segment": ["standard"] * 50,
            "activity_hour": [12] * 50,
            "is_impulsive": [False] * 50,
            "purchase_frequency": [1.0] * 50,
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

    boot_config = BootstrapConfig(
        n_runs=2, n_ticks_per_run=12, run_id_prefix="bootstrap-slow"
    )
    run_roots = run_bootstrap_simulation(
        boot_config,
        base_dir=tmp_path,
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
    )
    assert len(run_roots) == boot_config.n_runs

    df = collect_bootstrap_training_frame(
        run_roots,
        sellers_df=sellers,
        spec=FeatureSpec.v1_default(),
        config=CatBoostRepricingConfig(),
    )
    assert df.height > 0
    assert LABEL_COL in df.columns
    assert "RatingMaximizer" not in set(df[COL_STRATEGY_TYPE].cast(pl.String).to_list())
