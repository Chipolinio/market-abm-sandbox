# Назначение файла: Lossy WebSocket Broadcaster (Slice 6.3).
# Базовая идея: ConnectionManager рассылает фреймы 1Hz через asyncio.create_task
# с защитой от backpressure, зависших сокетов и disconnect-лавин.
from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any, Final

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect

from market_abm.api.schemas import TickStreamPayload

# Таймаут одиночной отправки на сокет (секунд).
# Вынесен в константу — тесты перекрывают через patch.
_SEND_TIMEOUT: Final[float] = 1.0


def compute_sleep_duration(elapsed: float, target: float = 1.0) -> float:
    """
    Вычисляет задержку до следующей итерации цикла 1Hz с компенсацией дрейфа.
    Никогда не возвращает отрицательное значение.
    """
    return max(0.0, target - elapsed)


async def _safely_send_text(
    ws: WebSocket,
    payload: str,
    manager: "ConnectionManager",
) -> None:
    """
    Отправляет строку клиенту с жёстким таймаутом.
    При любой ошибке (WebSocketDisconnect, TimeoutError, Exception)
    атомарно удаляет сокет из менеджера — наружу не пробрасывает.
    """
    try:
        await asyncio.wait_for(ws.send_text(payload), timeout=_SEND_TIMEOUT)
    except (WebSocketDisconnect, TimeoutError, Exception):
        manager.disconnect(ws)


class ConnectionManager:
    """
    Реестр активных WebSocket-соединений.
    Все методы работают в одном event loop FastAPI — блокировки не нужны.
    """

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        """Принимает WS-соединение и регистрирует его."""
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Удаляет сокет из реестра. Безопасен при повторном вызове."""
        self.active_connections = [
            ws for ws in self.active_connections if ws is not websocket
        ]

    async def broadcast(self, serialized_payload: str) -> None:
        """
        Рассылает уже сериализованный JSON всем подключённым клиентам.
        Итерирует по КОПИИ реестра — защита от Disconnect Avalanche.
        Каждая отправка изолирована в asyncio.create_task — защита от Hungry Socket.
        """
        for ws in self.active_connections.copy():
            asyncio.create_task(_safely_send_text(ws, serialized_payload, self))


async def broadcaster_loop(
    manager: ConnectionManager,
    tick_counter: Any,
    get_payload_fn: Callable[[int], TickStreamPayload],
    *,
    _target_hz: float = 1.0,
) -> None:
    """
    Lossy-цикл стриминга (1Hz по умолчанию).

    Контракты:
    - Сериализация JSON — ровно один раз на итерацию (не per-socket).
    - Типы NumPy/Rust кастуются к Python перед сериализацией внутри get_payload_fn.
    - Дрейф времени компенсируется через compute_sleep_duration.
    - asyncio.CancelledError не перехватывается — корректная отмена Task.
    """
    target_interval = 1.0 / _target_hz
    while True:
        start_time = time.monotonic()

        if manager.active_connections:
            tick_id = int(tick_counter.value)
            try:
                payload: TickStreamPayload = get_payload_fn(tick_id)
                # Единственная сериализация на итерацию — до цикла по клиентам
                serialized = payload.model_dump_json()
                await manager.broadcast(serialized)
            except Exception:  # noqa: BLE001
                pass

        elapsed = time.monotonic() - start_time
        await asyncio.sleep(compute_sleep_duration(elapsed, target=target_interval))
