# Тесты E2E интеграции (Slice 6.5).
# Стратегия: проверяем make_payload_fn, импорт main.py, lifespan-shutdown.
# Без реального spawn-процесса и без файловой системы Parquet.
from __future__ import annotations

import datetime
import multiprocessing as mp
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.domain.constants import COL_TICK_ID
from market_abm.worker.process import WorkerCommand, WorkerState


def _make_mock_store(
    *,
    mean_price: float = 0.0,
    total_gmv: float = 0.0,
    total_transactions: int = 0,
    drift_alerts: list[dict] | None = None,
) -> MagicMock:
    store = MagicMock()
    store._has_parquet_files.return_value = True
    store.query_market_aggregate.return_value = {
        "mean_price": mean_price,
        "total_gmv": total_gmv,
        "total_transactions": total_transactions,
    }
    store.drift_alerts.return_value = drift_alerts or []
    store.products_snapshot_at_tick.return_value = pl.DataFrame()
    store.gmv_by_tick.return_value = pl.DataFrame(
        schema={COL_TICK_ID: pl.Int32, "gmv": pl.Float64, "transaction_count": pl.Int64}
    )
    store.recent_system_events.return_value = []
    return store


def _make_mock_worker(
    state: WorkerState = WorkerState.IDLE,
    tick: int = 0,
) -> MagicMock:
    worker = MagicMock()
    worker.command_queue = MagicMock()
    worker.shock_queue = MagicMock()
    worker.process = MagicMock()
    worker.process.is_alive.side_effect = [True, False]
    worker.tick_counter = mp.Value("i", tick)
    worker.state = state
    worker.last_error = None
    worker.run_id = "test-run"
    return worker


def test_make_payload_fn_returns_callable() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store()
    fn = make_payload_fn(store)
    assert callable(fn)


def test_make_payload_fn_returns_valid_tick_stream_payload() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store(mean_price=100.0, total_gmv=5000.0, total_transactions=50)
    fn = make_payload_fn(store)
    payload = fn(5)

    assert isinstance(payload, TickStreamPayload)
    assert payload.tick_id == 5
    assert payload.market_summary.mean_price == pytest.approx(100.0)
    assert payload.market_summary.total_gmv == pytest.approx(5000.0)
    assert payload.market_summary.total_transactions == 50


def test_make_payload_fn_zero_aggregate_returns_zero_dto() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store()
    fn = make_payload_fn(store)
    payload = fn(0)

    assert payload.market_summary.mean_price == pytest.approx(0.0)
    assert payload.market_summary.total_gmv == pytest.approx(0.0)
    assert payload.market_summary.total_transactions == 0


def test_make_payload_fn_forwards_drift_alerts() -> None:
    from market_abm.main import make_payload_fn

    alerts = [{"feature": "price", "severity": "high"}, {"feature": "gmv", "severity": "low"}]
    store = _make_mock_store(drift_alerts=alerts)
    fn = make_payload_fn(store)
    payload = fn(1)

    assert payload.active_drift_alerts == alerts


def test_make_payload_fn_empty_drift_alerts_when_store_returns_empty() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store(drift_alerts=[])
    fn = make_payload_fn(store)
    payload = fn(1)

    assert payload.active_drift_alerts == []


def test_make_payload_fn_timestamp_utc_is_valid_iso_string() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store()
    fn = make_payload_fn(store)
    payload = fn(7)

    assert isinstance(payload.timestamp_utc, str)
    parsed = datetime.datetime.fromisoformat(payload.timestamp_utc)
    assert parsed.tzinfo is not None


def test_make_payload_fn_tick_id_passed_to_store_query() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store()
    fn = make_payload_fn(store)
    fn(42)

    store.query_market_aggregate.assert_any_call(42)
    store.query_market_aggregate.assert_any_call(0)


def test_make_payload_fn_calls_drift_alerts_once_per_call() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store()
    fn = make_payload_fn(store)
    fn(1)
    fn(2)

    assert store.drift_alerts.call_count == 2


def test_make_payload_fn_market_summary_is_market_aggregate_dto() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store(mean_price=10.0, total_gmv=100.0, total_transactions=5)
    fn = make_payload_fn(store)
    payload = fn(3)

    assert isinstance(payload.market_summary, MarketAggregateDTO)


def test_make_payload_fn_serializable_via_model_dump_json() -> None:
    from market_abm.main import make_payload_fn

    store = _make_mock_store(mean_price=9.99, total_gmv=999.0, total_transactions=100)
    fn = make_payload_fn(store)
    payload = fn(10)

    serialized = payload.model_dump_json()
    assert isinstance(serialized, str)
    assert '"tick_id"' in serialized
    assert '"market_summary"' in serialized


def test_main_module_is_importable() -> None:
    import importlib

    mod = importlib.import_module("market_abm.main")
    assert mod is not None


def test_main_exports_make_payload_fn_callable() -> None:
    from market_abm.main import make_payload_fn

    assert callable(make_payload_fn)


def test_main_exports_configure_multiprocessing_callable() -> None:
    from market_abm.main import configure_multiprocessing

    assert callable(configure_multiprocessing)


def test_configure_multiprocessing_sets_spawn_method() -> None:
    from market_abm.main import configure_multiprocessing

    with patch("multiprocessing.set_start_method") as mock_set:
        configure_multiprocessing()
        mock_set.assert_called_once_with("spawn", force=True)


def test_lifespan_sends_stop_command_to_worker_on_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.command_queue.put_nowait.assert_called_with(WorkerCommand.STOP)


def test_lifespan_calls_process_join_with_timeout_on_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.process.join.assert_called_once_with(timeout=5.0)


def test_lifespan_closes_command_queue_on_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.command_queue.close.assert_called_once()


def test_lifespan_closes_shock_queue_on_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.shock_queue.close.assert_called_once()


def test_lifespan_calls_join_thread_on_command_queue_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.command_queue.join_thread.assert_called_once()


def test_lifespan_stop_sent_before_join() -> None:
    """STOP уходит в очередь до вызова join — порядок операций корректный."""
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    call_order: list[str] = []

    worker = _make_mock_worker()
    store = _make_mock_store()

    worker.command_queue.put_nowait.side_effect = lambda _: call_order.append("stop")
    worker.process.join.side_effect = lambda **_: call_order.append("join")

    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    assert call_order.index("stop") < call_order.index("join")


def test_lifespan_shutdown_does_not_raise_if_queue_full() -> None:
    """Если очередь уже заполнена при shutdown — исключение не пробрасывается."""
    import queue as queue_module

    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()

    worker.command_queue.put_nowait.side_effect = queue_module.Full

    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass


def test_lifespan_starts_worker_process_when_flag_is_true() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store), start_worker=True)

    with TestClient(app):
        pass

    worker.process.start.assert_called_once()


def test_lifespan_does_not_start_worker_process_by_default() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app
    from market_abm.main import make_payload_fn

    worker = _make_mock_worker()
    store = _make_mock_store()
    app = create_app(worker=worker, get_payload_fn=make_payload_fn(store))

    with TestClient(app):
        pass

    worker.process.start.assert_not_called()


def test_app_module_level_object_is_fastapi_instance() -> None:
    from fastapi import FastAPI

    from market_abm.main import app as module_app

    assert isinstance(module_app, FastAPI)


def test_make_lazy_payload_fn_returns_zero_dto_before_manifest_exists(tmp_path: Path) -> None:
    from market_abm.main import make_lazy_payload_fn

    payload_fn = make_lazy_payload_fn(str(tmp_path / "nonexistent"))
    payload = payload_fn(0)

    assert isinstance(payload, TickStreamPayload)
    assert payload.market_summary.mean_price == pytest.approx(0.0)
    assert payload.market_summary.total_transactions == 0
    assert payload.market_summary.price_quantiles is None


def test_make_lazy_payload_fn_returns_stub_when_manifest_without_parquet(tmp_path: Path) -> None:
    import json

    from market_abm.main import make_lazy_payload_fn

    run_root = tmp_path / "stub-run"
    (run_root / "transactions").mkdir(parents=True)
    (run_root / "products_snapshots").mkdir()
    (run_root / "manifest.json").write_text(
        json.dumps({"run_id": "stub-run", "drift_alerts": []}),
        encoding="utf-8",
    )

    payload = make_lazy_payload_fn(str(run_root))(3)

    assert payload.market_summary.mean_price != pytest.approx(0.0)
    assert payload.market_summary.price_quantiles is not None


def test_make_lazy_payload_fn_reads_store_when_parquet_exists(tmp_path: Path) -> None:
    from market_abm.main import make_lazy_payload_fn

    from tests.helpers.mini_run import build_mini_run

    run_root = build_mini_run(tmp_path, run_id="lazy-e2e")
    payload = make_lazy_payload_fn(str(run_root))(0)

    assert payload.market_summary.mean_price == pytest.approx(150.0, rel=0.02)
    assert payload.market_summary.price_quantiles is not None
    assert payload.market_summary.total_transactions == 1


def test_make_lazy_payload_fn_is_callable() -> None:
    from market_abm.main import make_lazy_payload_fn

    fn = make_lazy_payload_fn("/tmp/any_dir")
    assert callable(fn)


def test_create_app_with_worker_factory_calls_factory_on_lifespan_start() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app

    created: list[object] = []

    def _factory() -> object:
        w = _make_mock_worker()
        created.append(w)
        return w

    app = create_app(worker_factory=_factory)

    with TestClient(app):
        pass

    assert len(created) == 1, "factory должна быть вызвана ровно один раз"


def test_create_app_worker_factory_wires_worker_into_app_state() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app

    produced_worker = _make_mock_worker()

    app = create_app(worker_factory=lambda: produced_worker)

    with TestClient(app) as client:
        resp = client.get("/api/v1/simulation/status")
        assert resp.status_code == 200


def test_create_app_worker_factory_starts_process_when_start_worker_true() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app

    worker = _make_mock_worker()

    app = create_app(worker_factory=lambda: worker, start_worker=True)

    with TestClient(app):
        pass

    worker.process.start.assert_called_once()


def test_create_app_worker_factory_sends_stop_on_shutdown() -> None:
    from fastapi.testclient import TestClient

    from market_abm.api.app import create_app

    worker = _make_mock_worker()

    app = create_app(worker_factory=lambda: worker)

    with TestClient(app):
        pass

    worker.command_queue.put_nowait.assert_called_with(WorkerCommand.STOP)


def test_module_level_app_uses_worker_factory_not_module_level_worker() -> None:
    """Модульный app не должен хранить воркер как глобальную переменную."""
    import market_abm.main as main_mod

    assert not hasattr(main_mod, "_worker"), (
        "_worker не должен существовать как модульная переменная — утечка семафоров при --reload"
    )
