# Назначение файла: smoke live worker — headroom preset и падение p50 при severe crash (Spec 011 §5.2).
from __future__ import annotations

import json
import queue
from pathlib import Path

import polars as pl
import pytest

from market_abm.domain.constants import COL_PRICE
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand
from market_abm.worker.simulation_session import LiveSimulationSession, _worker_run_config


def _write_pending(tmp_path: Path) -> None:
    pending = {
        "n_buyers": 400,
        "n_sellers": 24,
        "seed": 42,
    }
    (tmp_path / "pending_session.json").write_text(json.dumps(pending), encoding="utf-8")


def _tick_price_median(run_root: Path, tick_id: int) -> float:
    path = run_root / "products_snapshots" / f"tick_{tick_id:06d}.parquet"
    assert path.is_file(), f"missing products snapshot for tick {tick_id}"
    products = pl.read_parquet(path)
    assert products.height > 0
    return float(products[COL_PRICE].median())


def test_worker_run_config_uses_headroom_presets(tmp_path: Path) -> None:
    config = _worker_run_config(tmp_path)

    assert config.repricing.min_listing_price == pytest.approx(5.0)


def test_live_session_severe_crash_lowers_price_p50(tmp_path: Path) -> None:
    """Live worker: median listing price drops after severe demand crash (headroom preset)."""
    _write_pending(tmp_path)
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    warmup_end = 9
    shock_tick = 10
    stress_end = 29

    for tick_id in range(warmup_end + 1):
        session.run_tick(tick_id)

    p50_baseline = _tick_price_median(tmp_path, warmup_end)
    assert p50_baseline > 5.0

    shock_queue.put_nowait(
        ShockCommand(
            ShockType.DEMAND_CRASH,
            intensity=1.0,
            duration_ticks=0,
            scenario="severe",
        )
    )

    stress_medians: list[float] = []
    for tick_id in range(shock_tick, stress_end + 1):
        session.run_tick(tick_id)
        stress_medians.append(_tick_price_median(tmp_path, tick_id))

    p50_trough = min(stress_medians)
    assert p50_trough < p50_baseline * 0.97

    session.close()
