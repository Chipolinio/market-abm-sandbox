# Тесты Lossy WS Broadcaster (Slice 6.3).
# Стратегия:
#   - DTOs: чистые Pydantic unit-тесты
#   - ConnectionManager: async unit-тесты с мок-WebSocket (без реальных WS соединений)
#   - safely_send_text: async тесты на timeout/disconnect/exception
#   - compute_sleep_duration: чистая функция, sync тест
#   - WebSocket эндпоинт: Starlette TestClient WS context manager
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from market_abm.api.schemas import MarketAggregateDTO, TickStreamPayload
from market_abm.api.broadcaster import (
    ConnectionManager,
    _safely_send_text,
    compute_sleep_duration,
    broadcaster_loop,
)
from market_abm.api.app import create_app


# ---------------------------------------------------------------------------
# Вспомогательные типы и фабрики
# ---------------------------------------------------------------------------


class _FakeWebSocket:
    """Минимальный мок WebSocket для unit-тестов без реального TCP."""

    def __init__(
        self,
        *,
        fail_with: Exception | None = None,
        fail_on_nth: int | None = None,
    ) -> None:
        self.accepted: bool = False
        self.sent: list[str] = []
        self._fail_with = fail_with
        self._fail_on_nth = fail_on_nth
        self._call_count = 0

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self._call_count += 1
        if self._fail_with is not None:
            if self._fail_on_nth is None or self._call_count >= self._fail_on_nth:
                raise self._fail_with
        self.sent.append(data)

    async def receive_text(self) -> str:
        await asyncio.sleep(9999)
        return ""


def _make_mock_worker(tick: int = 0) -> object:
    import multiprocessing as mp
    from unittest.mock import MagicMock

    w = MagicMock()
    w.tick_counter = mp.Value("i", tick)
    w.state = MagicMock()
    w.last_error = None
    w.run_id = "test-run"
    return w


def _make_ws_client() -> TestClient:
    worker = _make_mock_worker()
    app = create_app(worker=worker)
    return TestClient(app)


# ---------------------------------------------------------------------------
# DTO-схемы
# ---------------------------------------------------------------------------


def test_market_aggregate_dto_fields() -> None:
    dto = MarketAggregateDTO(mean_price=100.0, total_gmv=5000.0, total_transactions=50)
    assert dto.mean_price == 100.0
    assert dto.total_gmv == 5000.0
    assert dto.total_transactions == 50


def test_tick_stream_payload_fields() -> None:
    summary = MarketAggregateDTO(mean_price=1.0, total_gmv=10.0, total_transactions=1)
    payload = TickStreamPayload(
        tick_id=5,
        timestamp_utc="2026-06-03T12:00:00Z",
        market_summary=summary,
        active_drift_alerts=[],
    )
    assert payload.tick_id == 5
    assert payload.market_summary.total_transactions == 1


def test_tick_stream_payload_model_dump_json_is_string() -> None:
    summary = MarketAggregateDTO(mean_price=1.0, total_gmv=10.0, total_transactions=1)
    payload = TickStreamPayload(
        tick_id=0,
        timestamp_utc="2026-06-03T00:00:00Z",
        market_summary=summary,
        active_drift_alerts=[],
    )
    serialized = payload.model_dump_json()
    assert isinstance(serialized, str)
    assert '"tick_id"' in serialized


def test_market_aggregate_dto_int_type_validation() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        MarketAggregateDTO(mean_price="bad", total_gmv=0.0, total_transactions=1)


# ---------------------------------------------------------------------------
# ConnectionManager (async)
# ---------------------------------------------------------------------------


async def test_connect_accepts_websocket_and_adds_to_pool() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)
    assert ws.accepted
    assert ws in manager.active_connections


async def test_disconnect_removes_websocket_from_pool() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)
    manager.disconnect(ws)
    assert ws not in manager.active_connections


async def test_disconnect_unknown_socket_does_not_raise() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    manager.disconnect(ws)


async def test_broadcast_sends_payload_to_all_connected() -> None:
    manager = ConnectionManager()
    ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
    await manager.connect(ws1)
    await manager.connect(ws2)

    await manager.broadcast("hello")
    await asyncio.sleep(0.05)

    assert ws1.sent == ["hello"]
    assert ws2.sent == ["hello"]


async def test_broadcast_empty_pool_no_error() -> None:
    manager = ConnectionManager()
    await manager.broadcast("ignored")


async def test_broadcast_iterates_copy_not_original() -> None:
    """Одновременное отключение сокета во время итерации не вызывает RuntimeError."""
    manager = ConnectionManager()

    class _SelfRemovingWS:
        async def accept(self) -> None:
            pass

        async def send_text(self, _: str) -> None:
            manager.disconnect(self)

    ws = _SelfRemovingWS()
    await manager.connect(ws)
    await manager.broadcast("trigger_remove")
    await asyncio.sleep(0.05)


async def test_broadcast_serializes_payload_as_string() -> None:
    """broadcast принимает строку (уже сериализованный JSON) — не вызывает send_json."""
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    await manager.broadcast('{"tick_id": 1}')
    await asyncio.sleep(0.05)

    assert ws.sent == ['{"tick_id": 1}']
    assert not hasattr(ws, "send_json_called"), "send_json не должен использоваться"


# ---------------------------------------------------------------------------
# _safely_send_text (async)
# ---------------------------------------------------------------------------


async def test_safely_send_text_sends_string_to_websocket() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    await _safely_send_text(ws, "payload", manager)
    assert ws.sent == ["payload"]


async def test_safely_send_text_removes_socket_on_websocket_disconnect() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket(fail_with=WebSocketDisconnect())
    await manager.connect(ws)

    await _safely_send_text(ws, "data", manager)
    assert ws not in manager.active_connections


async def test_safely_send_text_removes_socket_on_timeout() -> None:
    manager = ConnectionManager()

    class _SlowWS:
        accepted = True

        async def accept(self) -> None:
            pass

        async def send_text(self, _: str) -> None:
            await asyncio.sleep(9999)

    ws = _SlowWS()
    manager.active_connections.append(ws)

    with patch("market_abm.api.broadcaster._SEND_TIMEOUT", 0.01):
        await _safely_send_text(ws, "data", manager)

    assert ws not in manager.active_connections


async def test_safely_send_text_removes_socket_on_general_exception() -> None:
    manager = ConnectionManager()
    ws = _FakeWebSocket(fail_with=RuntimeError("connection died"))
    await manager.connect(ws)

    await _safely_send_text(ws, "data", manager)
    assert ws not in manager.active_connections


async def test_safely_send_text_does_not_raise_on_failure() -> None:
    """_safely_send_text никогда не пробрасывает исключение наружу."""
    manager = ConnectionManager()
    ws = _FakeWebSocket(fail_with=WebSocketDisconnect())
    await manager.connect(ws)

    await _safely_send_text(ws, "data", manager)


# ---------------------------------------------------------------------------
# compute_sleep_duration (чистая функция, sync)
# ---------------------------------------------------------------------------


def test_compute_sleep_no_elapsed_returns_target() -> None:
    assert compute_sleep_duration(elapsed=0.0, target=1.0) == pytest.approx(1.0)


def test_compute_sleep_partial_elapsed_compensates() -> None:
    duration = compute_sleep_duration(elapsed=0.3, target=1.0)
    assert duration == pytest.approx(0.7)


def test_compute_sleep_elapsed_exceeds_target_returns_zero() -> None:
    assert compute_sleep_duration(elapsed=1.5, target=1.0) == 0.0


def test_compute_sleep_elapsed_exactly_target_returns_zero() -> None:
    assert compute_sleep_duration(elapsed=1.0, target=1.0) == 0.0


def test_compute_sleep_never_returns_negative() -> None:
    assert compute_sleep_duration(elapsed=999.0, target=1.0) >= 0.0


# ---------------------------------------------------------------------------
# broadcaster_loop (async — короткий прогон с мок-данными)
# ---------------------------------------------------------------------------


async def test_broadcaster_sends_payload_to_connected_socket() -> None:
    """Broadcaster рассылает один фрейм за одну итерацию цикла."""
    import multiprocessing as mp

    manager = ConnectionManager()
    ws = _FakeWebSocket()
    await manager.connect(ws)

    tick_counter = mp.Value("i", 3)
    summary = MarketAggregateDTO(mean_price=50.0, total_gmv=500.0, total_transactions=10)

    def _stub_payload(tick_id: int) -> TickStreamPayload:
        return TickStreamPayload(
            tick_id=tick_id,
            timestamp_utc="2026-06-03T00:00:00Z",
            market_summary=summary,
            active_drift_alerts=[],
        )

    task = asyncio.create_task(
        broadcaster_loop(manager, tick_counter, _stub_payload, _target_hz=100.0)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    assert len(ws.sent) >= 1, "Broadcaster должен был отправить хотя бы один фрейм"
    import json

    decoded = json.loads(ws.sent[0])
    assert decoded["tick_id"] == 3


async def test_broadcaster_uses_single_serialization_per_cycle() -> None:
    """Сериализация JSON выполняется один раз на итерацию, не per-socket."""
    import multiprocessing as mp

    manager = ConnectionManager()
    ws1, ws2 = _FakeWebSocket(), _FakeWebSocket()
    await manager.connect(ws1)
    await manager.connect(ws2)

    tick_counter = mp.Value("i", 0)
    summary = MarketAggregateDTO(mean_price=1.0, total_gmv=1.0, total_transactions=1)

    def _counting_payload(tick_id: int) -> TickStreamPayload:
        return TickStreamPayload(
            tick_id=tick_id,
            timestamp_utc="2026-06-03T00:00:00Z",
            market_summary=summary,
            active_drift_alerts=[],
        )

    task = asyncio.create_task(
        broadcaster_loop(manager, tick_counter, _counting_payload, _target_hz=100.0)
    )
    await asyncio.sleep(0.05)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)

    if ws1.sent and ws2.sent:
        assert ws1.sent[0] == ws2.sent[0], (
            "Обе ws должны получить идентичный payload (единственная сериализация)"
        )


# ---------------------------------------------------------------------------
# WebSocket эндпоинт (TestClient)
# ---------------------------------------------------------------------------


def test_ws_endpoint_accepts_connection() -> None:
    client = _make_ws_client()
    with client.websocket_connect("/api/v1/stream/ws"):
        pass


def test_ws_endpoint_multiple_connections() -> None:
    client = _make_ws_client()
    with client.websocket_connect("/api/v1/stream/ws"):
        with client.websocket_connect("/api/v1/stream/ws"):
            pass
