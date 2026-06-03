# Назначение файла: WebSocket эндпоинт стриминга телеметрии (Slice 6.3).
# Базовая идея: endpoint только регистрирует/дерегистрирует соединение.
# Данные рассылает независимый asyncio.Task (broadcaster_loop), запущенный в lifespan.
from __future__ import annotations

from fastapi import APIRouter, Request, WebSocket
from fastapi.websockets import WebSocketDisconnect

from market_abm.api.broadcaster import ConnectionManager

router = APIRouter(tags=["stream"])


def _get_manager(request: Request) -> ConnectionManager:
    return request.app.state.ws_manager


@router.websocket("/api/v1/stream/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """
    Регистрирует WS-клиента в ConnectionManager.
    Держит соединение до отключения клиента.
    Данные клиент получает от broadcaster_loop, работающего параллельно.
    """
    manager: ConnectionManager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        # Блокируем до разрыва соединения клиентом
        while True:
            await websocket.receive_text()
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        manager.disconnect(websocket)
