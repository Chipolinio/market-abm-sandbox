# Назначение файла: live simulation session для worker subprocess (Slice 8.4).
from __future__ import annotations

import json
import os
import queue
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Final

import polars as pl

from market_abm.analytics.persist import (
    _config_hash,
    _write_manifest_atomic,
    clear_run_tick_artifacts,
    open_duckdb_connection,
    write_reference_snapshots,
)
from market_abm.config.buyers import BuyerPopulationConfig
from market_abm.config.repricing import ListingInitConfig, RepricingConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.config.sellers import SellerPopulationConfig
from market_abm.config.simulation import ChoiceModelConfig, SimulationStepConfig
from market_abm.population.buyers import generate_buyers
from market_abm.population.sellers import generate_sellers
from market_abm.simulation.context import drain_shock_queue, with_tick_id
from market_abm.simulation.extended_runtime import (
    ExtendedSimulationState,
    init_extended_state,
    persist_extended_tick,
)
from market_abm.simulation.listings import initialize_listings
from market_abm.simulation.runner import _bootstrap_products_from_listings, _bootstrap_rng
from market_abm.simulation.step import step
_WORKER_SEED: Final[int] = 42
_PENDING_SESSION_FILENAME: Final[str] = "pending_session.json"


def _read_pending_session(run_root: Path) -> dict[str, object] | None:
    pending_path = run_root / _PENDING_SESSION_FILENAME
    if not pending_path.is_file():
        return None
    try:
        payload = json.loads(pending_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _consume_pending_session(run_root: Path) -> dict[str, object] | None:
    pending = _read_pending_session(run_root)
    pending_path = run_root / _PENDING_SESSION_FILENAME
    if pending_path.is_file():
        pending_path.unlink(missing_ok=True)
    return pending


def _population_from_pending(
    pending: dict[str, object] | None,
    *,
    run_root: Path | None = None,
) -> tuple[int, int, int]:
    """Возвращает (n_buyers, n_sellers, seed); pending приоритетнее env defaults."""
    n_buyers = int(os.environ.get("WORKER_N_BUYERS", "300"))
    n_sellers = int(os.environ.get("WORKER_N_SELLERS", "30"))
    seed = _WORKER_SEED

    source = pending
    if source is None and run_root is not None:
        source = _read_pending_session(run_root)

    if source is not None:
        raw_buyers = source.get("n_buyers")
        if isinstance(raw_buyers, (int, float)) and not isinstance(raw_buyers, bool):
            n_buyers = int(raw_buyers)
        raw_sellers = source.get("n_sellers")
        if isinstance(raw_sellers, (int, float)) and not isinstance(raw_sellers, bool):
            n_sellers = int(raw_sellers)
        raw_seed = source.get("seed")
        if isinstance(raw_seed, (int, float)) and not isinstance(raw_seed, bool):
            seed = int(raw_seed)

    return n_buyers, n_sellers, seed


def _worker_n_buyers(run_root: Path | None = None) -> int:
    n_buyers, _, _ = _population_from_pending(None, run_root=run_root)
    return n_buyers


def _worker_n_sellers(run_root: Path | None = None) -> int:
    _, n_sellers, _ = _population_from_pending(None, run_root=run_root)
    return n_sellers


def _worker_run_config(run_root: Path) -> SimulationRunConfig:
    n_buyers, _, _ = _population_from_pending(None, run_root=run_root)
    # ChoiceModelConfig: buyers_batch_size gt=100 (config/simulation.py).
    buyers_batch_size = min(max(n_buyers, 101), 300)
    return SimulationRunConfig(
        seed=_WORKER_SEED,
        runtime_mode="extended",
        choice=ChoiceModelConfig(
            engine="numpy_softmax",
            max_products_per_choice_set=50,
            buyers_batch_size=buyers_batch_size,
            outside_utility_bias=-100.0,
            outside_utility_bias_by_pvd_segment=ChoiceModelConfig.default_segment_biases(),
        ),
        repricing=RepricingConfig.default_market(),
        persistence=PersistenceConfig(
            enabled=True,
            base_dir=str(run_root.parent),
            run_id=run_root.name,
        ),
    )


class LiveSimulationSession:
    """Один тик live-симуляции: drain shocks → step → persist → events."""

    def __init__(self, run_root: Path, shock_queue: queue.Queue) -> None:
        self._run_root = Path(run_root)
        self._shock_queue = shock_queue
        self._config = _worker_run_config(self._run_root)
        self._con = open_duckdb_connection(self._config.persistence)
        self._buyers_df: pl.DataFrame | None = None
        self._sellers_df: pl.DataFrame | None = None
        self._products_df: pl.DataFrame | None = None
        self._extended_state: ExtendedSimulationState | None = None
        self._last_external_tick: int | None = None
        self._run_id = self._run_root.name

    def close(self) -> None:
        self._con.close()

    def _hard_reset(self) -> None:
        clear_run_tick_artifacts(self._run_root)
        self._buyers_df = None
        self._sellers_df = None
        self._products_df = None
        self._extended_state = None
        self._last_external_tick = None

    def _write_initial_manifest(self, *, n_ticks: int) -> None:
        assert self._buyers_df is not None
        assert self._sellers_df is not None
        listings = initialize_listings(
            self._sellers_df,
            ListingInitConfig.default_market(),
            seed=_WORKER_SEED,
            min_listing_price=self._config.repricing.min_listing_price,
        )
        manifest: dict[str, object] = {
            "run_id": self._run_id,
            "created_at_utc": __import__("datetime").datetime.now(
                __import__("datetime").UTC
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_ticks": n_ticks,
            "seed": self._config.seed,
            "n_buyers": self._buyers_df.height,
            "n_sellers": self._sellers_df.height,
            "n_listings": listings.height,
            "config_hash": _config_hash(self._config),
            "engine": self._config.choice.engine,
            "ticks_completed": 0,
            "last_tick_id": None,
            "paths": {
                "transactions_glob": "transactions/tick_*.parquet",
                "products_glob": "products_snapshots/tick_*.parquet",
                "sellers_state_glob": "sellers_state/tick_*.parquet",
                "system_events_glob": "system_events/evt_*.parquet",
            },
        }
        _write_manifest_atomic(self._run_root, manifest)

    def _bootstrap_population(self) -> None:
        pending = _consume_pending_session(self._run_root)
        n_buyers, n_sellers, seed = _population_from_pending(pending)

        buyers_batch_size = min(max(n_buyers, 101), 300)
        if self._config.choice.buyers_batch_size != buyers_batch_size:
            self._config = self._config.model_copy(
                update={
                    "choice": self._config.choice.model_copy(
                        update={"buyers_batch_size": buyers_batch_size},
                    ),
                },
            )

        self._run_root.mkdir(parents=True, exist_ok=True)
        for sub in ("transactions", "products_snapshots", "sellers_state", "system_events"):
            (self._run_root / sub).mkdir(parents=True, exist_ok=True)

        self._buyers_df = generate_buyers(
            BuyerPopulationConfig.default_market(n_buyers=n_buyers, seed=seed)
        )
        self._sellers_df = generate_sellers(
            SellerPopulationConfig.default_market(n_sellers=n_sellers, seed=seed)
        )
        listings = initialize_listings(
            self._sellers_df,
            ListingInitConfig.default_market(),
            seed=seed,
            min_listing_price=self._config.repricing.min_listing_price,
        )
        rng = _bootstrap_rng(seed)
        self._products_df = _bootstrap_products_from_listings(
            listings,
            config=self._config.products_bootstrap,
            rng=rng,
            sellers_df=self._sellers_df,
        )
        self._extended_state = init_extended_state(self._sellers_df)
        write_reference_snapshots(
            self._run_root,
            buyers_df=self._buyers_df,
            sellers_df=self._sellers_df,
        )
        self._write_initial_manifest(n_ticks=1_000_000)

    def _tick_artifacts_exist(self, tick_id: int) -> bool:
        tx = self._run_root / "transactions" / f"tick_{tick_id:06d}.parquet"
        return tx.is_file()

    def run_tick(self, external_tick_index: int) -> None:
        """Выполняет ровно один тик симуляции (вызывается из _WorkerLoop)."""
        if self._tick_artifacts_exist(external_tick_index):
            if self._last_external_tick is None:
                # Новый subprocess / потеря памяти сессии при артефактах на диске.
                if external_tick_index == 0:
                    self._hard_reset()
                else:
                    raise RuntimeError(
                        f"Cannot resume tick {external_tick_index}: session memory was "
                        "lost but artifacts exist. Call RESET to start fresh."
                    )
            else:
                # Тот же subprocess: tick уже записан (desync tick_counter), пропускаем.
                self._last_external_tick = max(
                    self._last_external_tick,
                    external_tick_index,
                )
                return
        elif external_tick_index == 0 and self._last_external_tick is not None:
            self._hard_reset()

        if self._buyers_df is None:
            self._bootstrap_population()

        assert self._extended_state is not None
        assert self._products_df is not None
        assert self._buyers_df is not None
        assert self._sellers_df is not None

        tick_id = external_tick_index
        prev_sellers_state = self._extended_state.sellers_state_df

        self._extended_state = replace(
            self._extended_state,
            simulation_context=drain_shock_queue(
                self._shock_queue,
                with_tick_id(self._extended_state.simulation_context, tick_id),
            ),
        )
        sim_ctx = with_tick_id(self._extended_state.simulation_context, tick_id)

        step_config = SimulationStepConfig(
            tick_id=tick_id,
            seed=self._config.seed,
            choice=self._config.choice,
            repricing=self._config.repricing,
            economics=self._config.economics,
        )
        products_next, transactions_df, sellers_state_next = step(
            self._buyers_df,
            self._sellers_df,
            self._products_df,
            step_config,
            sellers_state_df=self._extended_state.sellers_state_df,
            simulation_context=sim_ctx,
            shock_catalog=self._config.shock_catalog,
        )
        if sellers_state_next is None:
            raise RuntimeError("extended worker session requires sellers_state_next")

        self._products_df = products_next
        self._extended_state = replace(
            self._extended_state,
            sellers_state_df=sellers_state_next,
            simulation_context=sim_ctx,
        )
        self._extended_state = persist_extended_tick(
            self._run_root,
            tick_id=tick_id,
            transactions_df=transactions_df,
            products_df=products_next,
            state=self._extended_state,
            prev_sellers_state=prev_sellers_state,
            config=self._config,
            con=self._con,
            run_id=self._run_id,
        )
        self._last_external_tick = external_tick_index


def make_live_step_fn(
    *,
    artifacts_dir: str,
    shock_queue: queue.Queue,
    tick_counter,
) -> Callable[[], None]:
    """
    Фабрика step_fn для _WorkerLoop / multiprocessing.Process.
    Замыкает LiveSimulationSession на весь жизненный цикл subprocess.
    """
    session = LiveSimulationSession(Path(artifacts_dir), shock_queue)

    def _step() -> None:
        session.run_tick(tick_counter.value)

    def reset_session() -> None:
        session._hard_reset()

    def close_session() -> None:
        session.close()

    _step.reset_session = reset_session  # type: ignore[attr-defined]
    _step.close_session = close_session  # type: ignore[attr-defined]
    return _step
