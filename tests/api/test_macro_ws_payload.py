# Spec 014 §13.1 — TickStreamPayload macro_state / active_shocks wire (slice 14.1).
from __future__ import annotations

import tempfile
from pathlib import Path

from market_abm.analytics.macro_snapshot import MacroSnapshotMemory, write_macro_snapshot
from market_abm.analytics.store import AnalyticsStore
from market_abm.api.schemas.stream import TickStreamPayload
from market_abm.api.stub_telemetry import stub_tick_payload, zero_tick_payload
from market_abm.config.macro import MacroDynamicsConfig
from market_abm.domain.macro import MacroRegime, MacroState
from market_abm.domain.shocks import ActiveShock, ShockType
from market_abm.main import make_payload_fn
from tests.helpers.mini_run import build_mini_run


def test_14_1_t3_ws_payload_idle_null_safe() -> None:
    stub = stub_tick_payload(0)
    assert stub.macro_state is None
    assert stub.active_shocks == []
    assert stub.ref_price is None

    zero = zero_tick_payload(0)
    assert zero.macro_state is None
    assert zero.active_shocks == []
    assert zero.ref_price is None

    raw = {
        "tick_id": 1,
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "market_summary": {
            "mean_price": 1.0,
            "total_gmv": 2.0,
            "total_transactions": 3,
            "price_quantiles": None,
        },
        "active_drift_alerts": [],
        "worker_state": "IDLE",
    }
    payload = TickStreamPayload.model_validate(raw)
    assert payload.macro_state is None
    assert payload.active_shocks == []
    assert payload.ref_price is None


def test_14_1_t2_ws_payload_includes_macro_and_shocks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp))
        store = AnalyticsStore(run_root)
        memory = MacroSnapshotMemory()
        store.attach_macro_memory(memory)

        macro = MacroState(
            stress=0.52,
            expansion=0.0,
            regime=MacroRegime.STRESS,
            peak_stress=0.52,
            peak_expansion=0.0,
            episode_id=1,
            ticks_in_episode=2,
        )
        shocks = (
            ActiveShock(
                shock_type=ShockType.DEMAND_CRASH,
                intensity=1.0,
                remaining_ticks=12,
                applied_at_tick=0,
                scenario="severe",
            ),
        )
        write_macro_snapshot(
            memory,
            tick_id=0,
            macro=macro,
            active_shocks=shocks,
            ref_price=None,
            config=MacroDynamicsConfig(),
        )

        try:
            payload = make_payload_fn(store)(0)
        finally:
            store.close()

    assert payload.macro_state is not None
    assert payload.macro_state.regime == "stress"
    assert payload.macro_state.stress == 0.52
    assert payload.macro_state.stress_cap == 1.2
    assert len(payload.active_shocks) >= 1
    assert payload.active_shocks[0].shock_type == "demand_crash"
    assert payload.active_shocks[0].scenario == "severe"
