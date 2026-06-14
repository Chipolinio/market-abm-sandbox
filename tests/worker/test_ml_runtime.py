# Назначение файла: live worker не вызывает fit в run_tick (Slice 11.5-T3, Spec 011 §5A.2).
from __future__ import annotations

import queue
from pathlib import Path
from unittest.mock import patch

from market_abm.worker.simulation_session import LiveSimulationSession
from tests.worker.conftest import write_pending_session


def test_11_5_t3_no_fit_in_run_tick(tmp_path: Path) -> None:
    """Spy fit_catboost_registry: call count 0 during live session ticks."""
    write_pending_session(tmp_path, {"n_buyers": 101, "n_sellers": 5, "seed": 1})
    shock_queue: queue.Queue = queue.Queue(maxsize=32)

    with patch("market_abm.ml.catboost_repricing.fit_catboost_registry") as fit_mock:
        session = LiveSimulationSession(tmp_path, shock_queue)
        try:
            session.run_tick(0)
            session.run_tick(1)
            fit_mock.assert_not_called()
        finally:
            session.close()
