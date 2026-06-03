# Тесты E2E интеграции (Slice 6.5).
# Стратегия: проверяем make_payload_fn, импорт main.py, lifespan-shutdown.
# Без реального spawn-процесса и без файловой системы Parquet.
from __future__ import annotations

import datetime
import multiprocessing as mp
from unittest.mock import MagicMock, patch

import pytest

from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.worker.process import WorkerCommand, WorkerState


def _make_mock_store(
    *,
    mean_price: float = 0.0,
    total_gmv: float = 0.0,
    total_transactions: int = 0,
    drift_alerts: list[dict] | None = None,
) -> MagicMock:
    store = MagicMock()
    store.query_market_aggregate.return_value = {
        "mean_price": mean_price,
        "total_gmv": total_gmv,
        "total_transactions": total_transactions,
    }
    store.drift_alerts.return_value = drift_alerts or []
    return store


def _make_mock_worker(
    state: WorkerState = WorkerState.IDLE,
    tick: int = 0,
) -> MagicMock:
    worker = MagicMock()
    worker.command_queue = MagicMock()
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

    store.query_market_aggregate.assert_called_once_with(42)


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


def test_make_lazy_payload_fn_returns_zero_dto_before_manifest_exists(
    tmp_path: "pytest.TempPathFactory",
) -> None:
    from market_abm.main import make_lazy_payload_fn

    payload_fn = make_lazy_payload_fn(str(tmp_path / "nonexistent"))
    payload = payload_fn(0)

    assert isinstance(payload, TickStreamPayload)
    assert payload.market_summary.mean_price == pytest.approx(0.0)
    assert payload.market_summary.total_transactions == 0


def test_make_lazy_payload_fn_is_callable() -> None:
    from market_abm.main import make_lazy_payload_fn

    fn = make_lazy_payload_fn("/tmp/any_dir")
    assert callable(fn)
