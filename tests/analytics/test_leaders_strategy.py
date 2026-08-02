# Назначение файла: honest leaders from strategy_type (Slice 11.7, Spec 011 §6, §13.7).
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from market_abm.analytics.leaders import query_market_leaders, write_sellers_state_snapshot
from market_abm.analytics.persist import (
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
    write_reference_snapshots,
)
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig
from market_abm.domain.constants import (
    ALGORITHM_TYPES,
    COL_BUYER_ID,
    COL_GROSS_MARGIN,
    COL_IS_BANKRUPT,
    COL_LISTING_ID,
    COL_MARGIN_FLOOR,
    COL_PRICE_PAID,
    COL_REPRICING_SPEED,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
    COL_UNIT_COST,
    COL_WORKING_CAPITAL,
    LOGIC_STATUS_DUMPING,
    SELLERS_COLUMNS,
    TRANSACTIONS_COLUMNS,
)
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.runner import (
    _bootstrap_products_from_listings,
    _bootstrap_rng,
    run_simulation_and_persist,
)
from market_abm.worker.simulation_session import _default_session_seed, _population_from_pending


def _write_leaders_run(
    tmp_path: Path,
    *,
    run_id: str,
    sellers_df: pl.DataFrame,
    sellers_state: pl.DataFrame,
    transactions: pl.DataFrame,
    seed: int = 1,
) -> Path:
    config = SimulationRunConfig(
        seed=seed,
        choice=ChoiceModelConfig(engine="numpy_softmax"),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id),
    )
    buyers_df = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=30, seed=seed))
    listings = initialize_listings(
        sellers_df,
        ListingInitConfig.default_market(),
        seed=seed,
        min_listing_price=config.repricing.min_listing_price,
    )
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers_df,
        sellers_df=sellers_df,
        listings_df=listings,
        n_ticks=1,
    )
    write_reference_snapshots(ctx.run_root, buyers_df=buyers_df, sellers_df=sellers_df)
    write_sellers_state_snapshot(ctx.run_root, tick_id=0, sellers_state_df=sellers_state)
    products_df = _bootstrap_products_from_listings(
        listings,
        config=config.products_bootstrap,
        rng=_bootstrap_rng(seed),
        sellers_df=sellers_df,
    )
    con = open_duckdb_connection(config.persistence)
    try:
        persist_tick_artifacts(
            ctx.run_root,
            tick_id=0,
            transactions_df=transactions,
            products_df=products_df,
            config=config.persistence,
            con=con,
        )
    finally:
        con.close()
    return ctx.run_root


def _sellers_row(
    seller_id: int,
    strategy: str,
    *,
    capital: float = 100.0,
) -> dict[str, object]:
    return {
        COL_SELLER_ID: seller_id,
        COL_STRATEGY_TYPE: strategy,
        "capital": capital,
        COL_MARGIN_FLOOR: 0.2,
        COL_REPRICING_SPEED: 1,
    }


def _sellers_df(rows: list[dict[str, object]]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_STRATEGY_TYPE).cast(pl.Categorical),
        pl.col("capital").cast(pl.Float32),
        pl.col(COL_MARGIN_FLOOR).cast(pl.Float32),
        pl.col(COL_REPRICING_SPEED).cast(pl.UInt8),
    ).select(list(SELLERS_COLUMNS))


def _state_row(seller_id: int, working_capital: float) -> dict[str, object]:
    return {
        COL_SELLER_ID: seller_id,
        COL_WORKING_CAPITAL: working_capital,
        COL_IS_BANKRUPT: False,
    }


def test_11_7_t1_logic_status_from_strategy_not_id_mod(tmp_path: Path) -> None:
    """MaxVolume seller_id=2 → dumping label, not id%3 RULE hash."""
    seller_id = 2
    assert ALGORITHM_TYPES[seller_id % len(ALGORITHM_TYPES)] == "RULE"

    sellers = _sellers_df([_sellers_row(seller_id, "MaxVolume")])
    sellers_state = pl.DataFrame([_state_row(seller_id, 500.0)]).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )
    tx = pl.DataFrame(
        {
            COL_TICK_ID: [0],
            COL_BUYER_ID: [0],
            COL_LISTING_ID: [seller_id],
            COL_SELLER_ID: [seller_id],
            COL_PRICE_PAID: [50.0],
            COL_UNIT_COST: [20.0],
            COL_GROSS_MARGIN: [30.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )

    run_root = _write_leaders_run(
        tmp_path,
        run_id="strategy-leaders",
        sellers_df=sellers,
        sellers_state=sellers_state,
        transactions=tx,
    )
    store = AnalyticsStore(run_root)
    try:
        raw = query_market_leaders(store, tick_id=0, limit=1)
    finally:
        store.close()

    leader = raw["leaders"][0]
    assert leader["strategy_type"] == "MaxVolume"
    assert leader["algorithm_type"] == "REPR"
    assert leader["logic_status"] == LOGIC_STATUS_DUMPING


def test_11_7_t2_rank_by_tick_revenue_changes_order(tmp_path: Path) -> None:
    sellers = _sellers_df(
        [
            _sellers_row(0, "MaxProfit"),
            _sellers_row(1, "MaxVolume"),
        ]
    )
    sellers_state = pl.DataFrame(
        [
            _state_row(0, 1000.0),
            _state_row(1, 200.0),
        ]
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )
    tx = pl.DataFrame(
        {
            COL_TICK_ID: [0, 0],
            COL_BUYER_ID: [0, 1],
            COL_LISTING_ID: [0, 1],
            COL_SELLER_ID: [0, 1],
            COL_PRICE_PAID: [10.0, 500.0],
            COL_UNIT_COST: [5.0, 5.0],
            COL_GROSS_MARGIN: [5.0, 495.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )

    run_root = _write_leaders_run(
        tmp_path,
        run_id="rank-by",
        sellers_df=sellers,
        sellers_state=sellers_state,
        transactions=tx,
    )
    store = AnalyticsStore(run_root)
    try:
        by_capital = query_market_leaders(
            store, tick_id=0, limit=2, rank_by="working_capital"
        )
        by_revenue = query_market_leaders(
            store, tick_id=0, limit=2, rank_by="tick_revenue"
        )
    finally:
        store.close()

    assert [row["seller_id"] for row in by_capital["leaders"]] == [0, 1]
    assert [row["seller_id"] for row in by_revenue["leaders"]] == [1, 0]


def test_tick_revenue_tiebreaks_by_cumulative_not_seller_id(tmp_path: Path) -> None:
    """Zero tick_revenue must not rank broke sellers above wealthy ones."""
    sellers = _sellers_df(
        [
            _sellers_row(0, "MaxVolume"),
            _sellers_row(1, "MaxProfit"),
            _sellers_row(2, "RatingMaximizer"),
        ]
    )
    sellers_state = pl.DataFrame(
        [
            _state_row(0, 15.0),
            _state_row(1, 2_300_000.0),
            _state_row(2, 12.0),
        ]
    ).with_columns(
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_WORKING_CAPITAL).cast(pl.Float32),
        pl.col(COL_IS_BANKRUPT).cast(pl.Boolean),
    )
    tx = pl.DataFrame(
        {
            COL_TICK_ID: [0],
            COL_BUYER_ID: [0],
            COL_LISTING_ID: [1],
            COL_SELLER_ID: [1],
            COL_PRICE_PAID: [100.0],
            COL_UNIT_COST: [20.0],
            COL_GROSS_MARGIN: [80.0],
        }
    ).with_columns(
        pl.col(COL_TICK_ID).cast(pl.Int32),
        pl.col(COL_BUYER_ID).cast(pl.Int32),
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
        pl.col(COL_PRICE_PAID).cast(pl.Float32),
        pl.col(COL_UNIT_COST).cast(pl.Float32),
        pl.col(COL_GROSS_MARGIN).cast(pl.Float32),
    )

    run_root = _write_leaders_run(
        tmp_path,
        run_id="tiebreak",
        sellers_df=sellers,
        sellers_state=sellers_state,
        transactions=tx,
    )
    store = AnalyticsStore(run_root)
    try:
        leaders = query_market_leaders(store, tick_id=0, limit=3, rank_by="tick_revenue")
    finally:
        store.close()

    assert [row["seller_id"] for row in leaders["leaders"]] == [1, 0, 2]
    assert leaders["leaders"][1]["cumulative_revenue"] == 0.0
    assert leaders["leaders"][1]["working_capital"] == 15.0


def _top3_seller_ids(tmp_path: Path, seed: int) -> tuple[int, ...]:
    run_id = f"seed-{seed}"
    config = SimulationRunConfig(
        seed=seed,
        runtime_mode="extended",
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=40,
            buyers_batch_size=150,
            outside_utility_bias=-100.0,
        ),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id),
    )
    buyers = generate_buyers(BuyerPopulationConfig.default_market(n_buyers=150, seed=seed))
    sellers = generate_sellers(SellerPopulationConfig.default_market(n_sellers=18, seed=seed))
    listings = initialize_listings(
        sellers,
        ListingInitConfig.default_market(),
        seed=seed,
        min_listing_price=config.repricing.min_listing_price,
    )
    gen = run_simulation_and_persist(buyers, sellers, listings, n_ticks=25, config=config)
    list(gen)
    store = AnalyticsStore(tmp_path / run_id)
    try:
        raw = query_market_leaders(store, tick_id=24, limit=3, rank_by="tick_revenue")
    finally:
        store.close()
    return tuple(int(row["seller_id"]) for row in raw["leaders"])


@pytest.mark.slow
def test_11_7_t3_seed_sweep_top3_not_identical(tmp_path: Path) -> None:
    """Seeds 0..9 → at least 3 distinct top-3 leader sets."""
    top3_sets = [_top3_seller_ids(tmp_path, seed) for seed in range(10)]
    assert all(len(row) > 0 for row in top3_sets)
    assert len(set(top3_sets)) >= 3


def test_worker_default_seed_varies_by_run_id() -> None:
    _, _, seed_a = _population_from_pending(None, run_root=Path("run-alpha"))
    _, _, seed_b = _population_from_pending(None, run_root=Path("run-beta"))
    assert seed_a != seed_b
    assert seed_a == _default_session_seed(Path("run-alpha"))
