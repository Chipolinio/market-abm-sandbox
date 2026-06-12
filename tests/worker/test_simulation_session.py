# Тесты LiveSimulationSession: прокидывание population params → manifest (Slice A.1).
from __future__ import annotations

import json
import queue
from pathlib import Path

import pytest

from market_abm.worker.simulation_session import (
    LiveSimulationSession,
    _worker_n_buyers,
    _worker_n_sellers,
)


def _write_pending_session(run_root: Path, payload: dict[str, object]) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    path = run_root / "pending_session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def _read_manifest(run_root: Path) -> dict[str, object]:
    return json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))


def test_worker_n_buyers_reads_pending_session(tmp_path: Path) -> None:
    _write_pending_session(tmp_path, {"n_buyers": 100})

    assert _worker_n_buyers(tmp_path) == 100


def test_worker_n_sellers_reads_pending_session(tmp_path: Path) -> None:
    _write_pending_session(tmp_path, {"n_sellers": 20})

    assert _worker_n_sellers(tmp_path) == 20


def test_worker_population_defaults_without_pending(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKER_N_BUYERS", raising=False)
    monkeypatch.delenv("WORKER_N_SELLERS", raising=False)

    assert _worker_n_buyers(tmp_path) == 300
    assert _worker_n_sellers(tmp_path) == 30


def test_live_session_manifest_reflects_pending_n_buyers(tmp_path: Path) -> None:
    _write_pending_session(tmp_path, {"n_buyers": 100, "n_sellers": 20, "seed": 42})
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    try:
        session.run_tick(0)
        manifest = _read_manifest(tmp_path)
        assert manifest["n_buyers"] == 100
        assert manifest["n_sellers"] == 20
    finally:
        session.close()


def test_start_request_population_size(tmp_path: Path) -> None:
    """Якорный acceptance: pending overlay n_buyers=100 → manifest n_buyers==100."""
    _write_pending_session(tmp_path, {"n_buyers": 100, "n_sellers": 15})
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    try:
        session.run_tick(0)
        manifest = _read_manifest(tmp_path)
        assert manifest["n_buyers"] == 100
    finally:
        session.close()


def test_live_session_produces_positive_gmv_on_first_tick(tmp_path: Path) -> None:
    """Regression: worker choice + economics must yield transactions (not all-outside)."""
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    try:
        session.run_tick(0)
        tx_path = tmp_path / "transactions" / "tick_000000.parquet"
        assert tx_path.is_file()
        import polars as pl

        tx = pl.read_parquet(tx_path)
        assert tx.height > 0
        assert float(tx["price_paid"].sum()) > 0.0
    finally:
        session.close()


def test_pending_session_consumed_after_bootstrap(tmp_path: Path) -> None:
    _write_pending_session(tmp_path, {"n_buyers": 250})
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    try:
        session.run_tick(0)
        assert not (tmp_path / "pending_session.json").is_file()
    finally:
        session.close()
