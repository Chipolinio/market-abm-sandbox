# Назначение файла: REST Control API — управление жизненным циклом симуляции (Slice 6.2).
# Базовая идея: FastAPI — stateless-прокси. Читает состояние из shared-memory воркера,
# пишет команды в Queue через asyncio.to_thread (защита Event Loop от блокировки).
from __future__ import annotations

import asyncio
import queue
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from market_abm.api.schemas import SimulationStartRequest, SimulationStatusResponse
from market_abm.worker.process import WorkerCommand, WorkerState

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])

# Метка времени старта приложения для elapsed_time_seconds
_APP_START_TIME: float = time.monotonic()


def _get_worker(request: Request) -> Any:
    return request.app.state.worker


async def _enqueue_command(cmd_queue: Any, command: WorkerCommand) -> None:
    """
    Ставит команду в Queue через asyncio.to_thread.
    Бросает HTTPException(429) если очередь заполнена.
    Бросает HTTPException(500) при непредвиденной ошибке.
    """

    def _put() -> None:
        try:
            cmd_queue.put_nowait(command)
        except queue.Full as exc:
            raise queue.Full from exc

    try:
        await asyncio.to_thread(_put)
    except queue.Full:
        raise HTTPException(
            status_code=429,
            detail="Command queue is full. Worker is busy processing previous command.",
        )


@router.post("/start", status_code=202)
async def start_simulation(
    body: SimulationStartRequest = SimulationStartRequest(),
    worker: Any = Depends(_get_worker),
) -> dict[str, str]:
    state: WorkerState = worker.state

    if state == WorkerState.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Simulation is already running.",
        )
    if state in (WorkerState.STOPPED, WorkerState.FAILED) and not body.force_clear:
        raise HTTPException(
            status_code=400,
            detail=(
                "Simulation finished. Use force_clear=True or call /reset "
                "to start a new session."
            ),
        )

    await _enqueue_command(worker.command_queue, WorkerCommand.START)
    return {"state": "accepted", "message": "START command enqueued"}


@router.post("/pause", status_code=202)
async def pause_simulation(
    worker: Any = Depends(_get_worker),
) -> dict[str, str]:
    state: WorkerState = worker.state

    if state != WorkerState.RUNNING:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot pause: simulation is in state {state.name!r}, expected RUNNING.",
        )

    await _enqueue_command(worker.command_queue, WorkerCommand.PAUSE)
    return {"state": "accepted", "message": "PAUSE command enqueued"}


@router.post("/step", status_code=202)
async def step_simulation(
    worker: Any = Depends(_get_worker),
) -> dict[str, str]:
    state: WorkerState = worker.state

    if state == WorkerState.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot step while running. Pause first.",
        )
    if state != WorkerState.PAUSED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot step: simulation is in state {state.name!r}, expected PAUSED.",
        )

    await _enqueue_command(worker.command_queue, WorkerCommand.STEP)
    return {"state": "accepted", "message": "STEP command enqueued"}


@router.post("/reset", status_code=202)
async def reset_simulation(
    worker: Any = Depends(_get_worker),
) -> dict[str, str]:
    state: WorkerState = worker.state

    if state == WorkerState.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Cannot reset while running. Stop or pause the simulation first.",
        )

    await _enqueue_command(worker.command_queue, WorkerCommand.RESET)
    return {"state": "accepted", "message": "RESET command enqueued"}


@router.get("/status", response_model=SimulationStatusResponse)
async def get_status(
    worker: Any = Depends(_get_worker),
) -> SimulationStatusResponse:
    state: WorkerState = worker.state
    return SimulationStatusResponse(
        run_id=getattr(worker, "run_id", "default"),
        state=state.name,
        current_tick=worker.tick_counter.value,
        elapsed_time_seconds=round(time.monotonic() - _APP_START_TIME, 3),
        last_error=worker.last_error,
    )
