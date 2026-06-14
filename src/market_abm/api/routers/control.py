# Назначение файла: REST Control API — управление жизненным циклом симуляции (Slice 6.2).
# Базовая идея: FastAPI — stateless-прокси. Читает состояние из shared-memory воркера,
# пишет команды в Queue через asyncio.to_thread (защита Event Loop от блокировки).
from __future__ import annotations

import asyncio
import json
import queue
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from market_abm.api.schemas import (
    SessionConfigureRequest,
    SessionConfigureResponse,
    SimulationShockRequest,
    SimulationShockResponse,
    SimulationStartRequest,
    SimulationStatusResponse,
)
from market_abm.config.session import SellerMixConfig
from market_abm.domain.shocks import ShockType
from market_abm.simulation.context import ShockCommand
from market_abm.worker.process import WorkerCommand, WorkerState

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])


def _shock_command_from_body(body: SimulationShockRequest) -> ShockCommand:
    """Maps REST body → pickle-safe ShockCommand (Spec 011 §8.4)."""
    duration = body.duration_ticks
    if duration is None:
        if body.shock_type in ("demand_crash", "demand_boom"):
            duration = 0
        else:
            duration = 10
    return ShockCommand(
        shock_type=ShockType(body.shock_type),
        intensity=body.intensity,
        duration_ticks=duration,
        scenario=body.scenario,
    )


def _get_worker(request: Request) -> Any:
    return request.app.state.worker


async def _enqueue_shock(shock_queue: Any, command: ShockCommand) -> int:
    """
    Ставит ShockCommand в shock_queue через asyncio.to_thread.
    Возвращает queue_depth после put. HTTP 429 при переполнении.
    """

    def _put() -> int:
        shock_queue.put_nowait(command)
        try:
            return shock_queue.qsize()
        except NotImplementedError:
            # macOS: mp.Queue.qsize() недоступен (sem_getvalue)
            return 1

    try:
        return await asyncio.to_thread(_put)
    except queue.Full:
        raise HTTPException(
            status_code=429,
            detail="Shock queue is full. Worker is busy processing previous shocks.",
        )


def _merge_start_pending(
    artifacts_dir: Path,
    body: SimulationStartRequest,
    *,
    explicit_fields: frozenset[str],
) -> None:
    """
    Записывает population overlay для worker bootstrap.
    Явные поля из JSON тела /start перетирают configure; неявные дефолты Pydantic — нет.
    """
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pending_path = artifacts_dir / "pending_session.json"
    existing: dict[str, object] = {}
    if pending_path.is_file():
        try:
            loaded = json.loads(pending_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
        except (json.JSONDecodeError, OSError):
            existing = {}

    payload = dict(existing)
    if "n_buyers" in explicit_fields:
        payload["n_buyers"] = body.n_buyers
    elif "n_buyers" not in payload:
        payload["n_buyers"] = body.n_buyers

    if "n_sellers" in explicit_fields:
        payload["n_sellers"] = body.n_sellers
    elif "n_sellers" not in payload:
        payload["n_sellers"] = body.n_sellers

    pending_path.write_text(json.dumps(payload), encoding="utf-8")


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


@router.post("/shock", status_code=202, response_model=SimulationShockResponse)
async def post_shock(
    body: SimulationShockRequest,
    worker: Any = Depends(_get_worker),
) -> SimulationShockResponse:
    shock_queue = getattr(worker, "shock_queue", None)
    if shock_queue is None:
        raise HTTPException(
            status_code=500,
            detail="Worker does not expose shock_queue.",
        )

    cmd = _shock_command_from_body(body)
    depth = await _enqueue_shock(shock_queue, cmd)
    return SimulationShockResponse(
        shock_type=body.shock_type,
        queue_depth=depth,
    )


@router.post("/configure", status_code=202, response_model=SessionConfigureResponse)
async def configure_session(
    body: SessionConfigureRequest,
    worker: Any = Depends(_get_worker),
) -> SessionConfigureResponse:
    state: WorkerState = worker.state

    if state == WorkerState.RUNNING:
        raise HTTPException(
            status_code=400,
            detail="Stop simulation before reconfiguring.",
        )

    artifacts_dir = Path(getattr(worker, "_artifacts_dir", "runs/default"))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pending_path = artifacts_dir / "pending_session.json"
    pending_path.write_text(body.model_dump_json(), encoding="utf-8")

    return SessionConfigureResponse(n_buyers=body.n_buyers, n_sellers=body.n_sellers)


_DEFAULT_SESSION_CONFIGURE = SessionConfigureRequest(
    n_buyers=10_000,
    n_sellers=50,
    seller_mix=SellerMixConfig(
        catboost_pct=0.4,
        rule_based_pct=0.35,
        basic_pct=0.25,
    ),
)


@router.get("/configure", response_model=SessionConfigureRequest)
async def get_session_configure(
    worker: Any = Depends(_get_worker),
) -> SessionConfigureRequest:
    """Pending session config (written by POST /configure) or defaults."""
    artifacts_dir = Path(getattr(worker, "_artifacts_dir", "runs/default"))
    pending_path = artifacts_dir / "pending_session.json"
    if pending_path.is_file():
        return SessionConfigureRequest.model_validate_json(
            pending_path.read_text(encoding="utf-8"),
        )
    return _DEFAULT_SESSION_CONFIGURE


@router.post("/start", status_code=202)
async def start_simulation(
    request: Request,
    worker: Any = Depends(_get_worker),
) -> dict[str, str]:
    try:
        raw_body = await request.json()
    except json.JSONDecodeError:
        raw_body = {}
    if not isinstance(raw_body, dict):
        raw_body = {}
    body = SimulationStartRequest.model_validate(raw_body)
    explicit_fields = frozenset(raw_body.keys())

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

    artifacts_dir = Path(getattr(worker, "_artifacts_dir", "runs/default"))
    _merge_start_pending(artifacts_dir, body, explicit_fields=explicit_fields)

    start_cmd = (
        WorkerCommand.START_FORCE_CLEAR
        if body.force_clear and state != WorkerState.RUNNING
        else WorkerCommand.START
    )
    await _enqueue_command(worker.command_queue, start_cmd)
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
        elapsed_time_seconds=round(
            getattr(worker, "elapsed_simulation_seconds", 0.0), 3
        ),
        last_error=worker.last_error,
    )
