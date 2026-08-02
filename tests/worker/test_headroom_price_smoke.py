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
    assert config.economics.fixed_cost_per_tick == pytest.approx(0.0)


def test_live_session_severe_crash_lowers_price_p50(tmp_path: Path) -> None:
    """Live worker: median listing price drops after severe demand crash (headroom preset)."""
    _write_pending(tmp_path)
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    warmup_end = 9
    shock_tick = 10
    stress_end = 35

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
    assert p50_trough < p50_baseline * 0.93

    session.close()


def _tick_quantiles(run_root: Path, tick_id: int) -> tuple[float, float, float, int]:
    path = run_root / "products_snapshots" / f"tick_{tick_id:06d}.parquet"
    assert path.is_file(), f"missing products snapshot for tick {tick_id}"
    products = pl.read_parquet(path)
    assert products.height > 0
    prices = products[COL_PRICE]
    return (
        float(prices.quantile(0.1)),
        float(prices.median()),
        float(prices.quantile(0.9)),
        products.height,
    )


def _write_pending_frontend_defaults(tmp_path: Path) -> None:
    pending = {
        "n_buyers": 10_000,
        "n_sellers": 50,
        "seed": 42,
    }
    (tmp_path / "pending_session.json").write_text(json.dumps(pending), encoding="utf-8")


def test_live_session_frontend_defaults_no_shock_stable_through_tick_60(
    tmp_path: Path,
) -> None:
    """Без шока каталог не схлопывается, а p50 не делает обрыв на ~40 тике (10k/50)."""
    _write_pending_frontend_defaults(tmp_path)
    session = LiveSimulationSession(tmp_path, queue.Queue(maxsize=8))

    p50_by_tick: list[float] = []
    counts: list[int] = []
    for tick_id in range(61):
        session.run_tick(tick_id)
        _, p50, _, n = _tick_quantiles(tmp_path, tick_id)
        p50_by_tick.append(p50)
        counts.append(n)

    assert min(counts) == max(counts) == 50
    assert p50_by_tick[40] >= p50_by_tick[39] * 0.98
    assert p50_by_tick[50] >= p50_by_tick[40] * 0.98
    assert p50_by_tick[60] >= p50_by_tick[30] * 0.92
    session.close()


def test_live_session_frontend_defaults_late_shock_moves_p50_and_p90(
    tmp_path: Path,
) -> None:
    _write_pending_frontend_defaults(tmp_path)
    shock_queue: queue.Queue = queue.Queue(maxsize=8)
    session = LiveSimulationSession(tmp_path, shock_queue)

    for tick_id in range(100):
        session.run_tick(tick_id)

    _, p50_pre, p90_pre, n_pre = _tick_quantiles(tmp_path, 99)
    assert n_pre == 50

    shock_queue.put_nowait(
        ShockCommand(
            ShockType.DEMAND_CRASH,
            intensity=1.0,
            duration_ticks=0,
            scenario="severe",
        )
    )

    for tick_id in range(100, 115):
        session.run_tick(tick_id)

    troughs = [_tick_quantiles(tmp_path, tick_id) for tick_id in range(100, 115)]
    p50_trough = min(row[1] for row in troughs)
    p90_trough = min(row[2] for row in troughs)

    assert p50_trough < p50_pre * 0.95
    assert p90_trough < p90_pre * 0.90
    session.close()


def test_live_session_no_shock_keeps_catalog_stable_through_warmup(tmp_path: Path) -> None:
    _write_pending(tmp_path)
    session = LiveSimulationSession(tmp_path, queue.Queue(maxsize=8))

    for tick_id in range(15):
        session.run_tick(tick_id)

    warmup_counts: list[int] = []
    for tick_id in range(15):
        path = tmp_path / "products_snapshots" / f"tick_{tick_id:06d}.parquet"
        products = pl.read_parquet(path)
        warmup_counts.append(products.height)

    assert min(warmup_counts) == max(warmup_counts) == 24
    session.close()
