# Назначение файла: stochastic shock API + cyber-log (Slice 11.8, Spec 011 §13.8).
from __future__ import annotations

import json
import multiprocessing as mp
import queue
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import polars as pl
from fastapi.testclient import TestClient

from market_abm.analytics.events import build_macro_demand_shock_event
from market_abm.api.app import create_app
from market_abm.config.macro import CrisisScenarioConfig, MacroDynamicsConfig
from market_abm.domain.events import COL_MESSAGE
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand, default_simulation_context, merge_shock
from market_abm.simulation.macro import apply_demand_impulse, crisis_scenario_config, macro_rng
from market_abm.worker.process import WorkerState
from market_abm.worker.simulation_session import LiveSimulationSession


def _make_mock_worker(state: WorkerState = WorkerState.IDLE) -> MagicMock:
    worker = MagicMock()
    worker.command_queue = mp.Queue(maxsize=1)
    worker.shock_queue = mp.Queue(maxsize=32)
    worker.tick_counter = mp.Value("i", 0)
    worker.state = state
    worker.last_error = None
    worker.run_id = "test-run"
    return worker


def test_11_8_t1_shock_without_duration_accepted() -> None:
    worker = _make_mock_worker()
    client = TestClient(create_app(worker=worker), raise_server_exceptions=True)

    resp = client.post(
        "/api/v1/simulation/shock",
        json={
            "shock_type": "demand_crash",
            "intensity": 1.0,
            "scenario": "standard",
        },
    )

    assert resp.status_code == 202
    cmd = worker.shock_queue.get_nowait()
    assert cmd.duration_ticks == 0
    assert cmd.scenario == "standard"

    ctx = merge_shock(default_simulation_context(), cmd)
    config = MacroDynamicsConfig(shock_mode="stochastic_regime", impulse_sigma=0.0)
    rng = macro_rng(42, 0, ctx.macro.episode_id)
    ctx_after = apply_demand_impulse(
        ctx,
        cmd,
        config,
        rng,
        scenario=crisis_scenario_config("standard"),
    )
    assert ctx_after.macro.stress > ctx.macro.stress


def test_11_8_t2_cyber_log_no_remaining_ticks_in_stochastic() -> None:
    event = build_macro_demand_shock_event(
        run_id="r1",
        tick_id=5,
        seq=0,
        shock_type=ShockType.DEMAND_CRASH,
        scenario="standard",
        impulse=0.45,
        stress=0.52,
        est_half_life_ticks=28.0,
    )
    message = str(event["message"]).lower()
    assert "stress elevated" in message
    assert "half-life" in message
    assert "10 ticks" not in message
    assert "remaining_ticks" not in message


def test_11_8_t3_scenario_severe_higher_peak_stress() -> None:
    config = MacroDynamicsConfig(shock_mode="stochastic_regime", impulse_sigma=0.0)
    rng = np.random.default_rng(99)

    def _peak_stress(scenario: str) -> float:
        ctx = default_simulation_context()
        cmd = ShockCommand(ShockType.DEMAND_CRASH, 1.0, 0, scenario=scenario)
        ctx = merge_shock(ctx, cmd)
        ctx = apply_demand_impulse(
            ctx,
            cmd,
            config,
            rng,
            scenario=crisis_scenario_config(scenario),
        )
        return ctx.macro.stress

    mild_stress = _peak_stress("mild")
    severe_stress = _peak_stress("severe")
    assert severe_stress > mild_stress
    assert severe_stress >= CrisisScenarioConfig.severe().impulse_mean * 0.9


def test_live_session_stochastic_cyber_log(tmp_path: Path) -> None:
    """Worker smoke: macro narrative in system_events after demand crash."""
    pending = {"n_buyers": 200, "n_sellers": 15, "seed": 42}
    (tmp_path / "pending_session.json").write_text(json.dumps(pending), encoding="utf-8")
    shock_queue: queue.Queue = queue.Queue(maxsize=32)
    session = LiveSimulationSession(tmp_path, shock_queue)

    session.run_tick(0)
    shock_queue.put_nowait(
        ShockCommand(ShockType.DEMAND_CRASH, intensity=1.0, duration_ticks=0, scenario="standard")
    )
    session.run_tick(1)

    fragments = list((tmp_path / "system_events").glob("evt_*.parquet"))
    assert fragments
    events = pl.read_parquet(fragments)
    demand_rows = events.filter(pl.col("display_code") == "DEMAND_SHOCK")
    assert demand_rows.height >= 1
    message = str(demand_rows[COL_MESSAGE][0]).lower()
    assert "stress" in message
    assert "10 ticks" not in message

    session.close()
