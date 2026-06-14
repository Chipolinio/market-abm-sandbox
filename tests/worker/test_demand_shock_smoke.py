# Spec 010 §10.6 — live session smoke: demand crash снижает GMV vs тик до шока.
from __future__ import annotations

import json
import queue
from pathlib import Path

import polars as pl

from market_abm.domain.constants import COL_PRICE_PAID
from market_abm.domain.events import COL_MESSAGE
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand
from market_abm.worker.simulation_session import LiveSimulationSession


def _write_pending(tmp_path: Path, *, n_buyers: int = 400, n_sellers: int = 20) -> None:
    pending = {
        "n_buyers": n_buyers,
        "n_sellers": n_sellers,
        "seed": 42,
    }
    (tmp_path / "pending_session.json").write_text(json.dumps(pending), encoding="utf-8")


def _tick_gmv(run_root: Path, tick_id: int) -> float:
    path = run_root / "transactions" / f"tick_{tick_id:06d}.parquet"
    if not path.is_file():
        return 0.0
    tx = pl.read_parquet(path)
    if tx.height == 0:
        return 0.0
    return float(tx[COL_PRICE_PAID].sum())


def _tick_transaction_count(run_root: Path, tick_id: int) -> int:
    path = run_root / "transactions" / f"tick_{tick_id:06d}.parquet"
    if not path.is_file():
        return 0
    return pl.read_parquet(path).height


def test_live_session_demand_crash_lowers_gmv(tmp_path: Path) -> None:
    _write_pending(tmp_path)
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    for tick_id in range(4):
        session.run_tick(tick_id)

    gmv_before = _tick_gmv(tmp_path, 3)
    txn_before = _tick_transaction_count(tmp_path, 3)
    assert gmv_before > 0.0
    assert txn_before > 0

    shock_queue.put_nowait(
        ShockCommand(ShockType.DEMAND_CRASH, intensity=1.0, duration_ticks=10)
    )
    session.run_tick(4)

    gmv_after = _tick_gmv(tmp_path, 4)
    txn_after = _tick_transaction_count(tmp_path, 4)

    assert gmv_after < gmv_before
    assert txn_after <= txn_before

    session.close()


def test_live_session_demand_crash_cyber_log_message(tmp_path: Path) -> None:
    _write_pending(tmp_path, n_buyers=200, n_sellers=15)
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    session.run_tick(0)
    shock_queue.put_nowait(
        ShockCommand(ShockType.DEMAND_CRASH, intensity=1.0, duration_ticks=5)
    )
    session.run_tick(1)

    events_dir = tmp_path / "system_events"
    fragments = list(events_dir.glob("evt_*.parquet"))
    assert fragments
    events = pl.read_parquet(fragments)
    demand_rows = events.filter(pl.col("display_code") == "DEMAND_SHOCK")
    assert demand_rows.height >= 1
    message = str(demand_rows[COL_MESSAGE][0]).lower()
    assert "budget" in message
    assert "active buyer rate" in message

    session.close()
