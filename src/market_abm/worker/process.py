# Назначение файла: изолированный процесс симуляции рынка (Slice 6.1).
# Базовая идея: SimulationWorker — тонкая обёртка над multiprocessing.Process.
# Вся логика стейт-машины сосредоточена в _WorkerLoop и тестируется через threading.
from __future__ import annotations

import importlib
import json
import multiprocessing as mp
import os
import queue
import time
from collections.abc import Callable
from enum import IntEnum
from enum import Enum
from pathlib import Path
from typing import Final

_SHOCK_QUEUE_MAXSIZE: Final[int] = 32

__all__ = [
    "SimulationWorker",
    "WorkerCommand",
    "WorkerState",
    "_WorkerLoop",
    "_noop_step",
]

_LOOP_CMD_TIMEOUT: Final[float] = 0.05   # секунд ожидания команды в PAUSED/IDLE
_RUNNING_STEP_YIELD_SEC: Final[float] = 0.05  # noop-stub: не крутить миллионы тиков/сек
_MANIFEST_FILENAME: Final[str] = "manifest.json"
_MANIFEST_TMP_SUFFIX: Final[str] = ".tmp"
_LAST_ERROR_ARRAY_SIZE: Final[int] = 2048


class WorkerState(IntEnum):
    """Состояния стейт-машины воркера."""

    IDLE = 0
    RUNNING = 1
    PAUSED = 2
    STOPPED = 3
    FAILED = 4


class WorkerCommand(str, Enum):
    """Команды управления воркером через IPC-очередь."""

    START = "start"
    PAUSE = "pause"
    STEP = "step"
    STOP = "stop"
    RESET = "reset"


def _noop_step() -> None:
    """Заглушка шага симуляции для изолированного тестирования воркера."""


class _WorkerLoop:
    """
    Внутренний цикл управления симуляцией.
    Принимает разделяемые примитивы (mp.Value, mp.Array, mp.Queue) и callable step_fn.
    Можно запускать как в multiprocessing.Process, так и в threading.Thread (для тестов).
    """

    def __init__(
        self,
        command_queue: mp.Queue,
        tick_counter: mp.Value,
        state_value: mp.Value,
        last_error_array: mp.Array,
        artifacts_dir: str,
        step_fn: Callable[[], None],
        running_since: mp.Value | None = None,
        elapsed_total: mp.Value | None = None,
    ) -> None:
        self._cmd_queue = command_queue
        self._tick_counter = tick_counter
        self._state_value = state_value
        self._last_error_array = last_error_array
        self._artifacts_dir = Path(artifacts_dir)
        self._step_fn = step_fn
        self._running_since: mp.Value = running_since or mp.Value("d", 0.0)
        self._elapsed_total: mp.Value = elapsed_total or mp.Value("d", 0.0)


    def run(self) -> None:
        """
        Главный цикл воркера. Запускается единожды (Process.run или Thread.run).
        Завершается при переходе в STOPPED или FAILED.
        """
        while True:
            state = WorkerState(self._state_value.value)

            if state == WorkerState.IDLE:
                self._wait_for_command()

            elif state == WorkerState.RUNNING:
                self._consume_pending_command_non_blocking()
                if WorkerState(self._state_value.value) != WorkerState.RUNNING:
                    continue
                self._safe_execute_step()
                time.sleep(_RUNNING_STEP_YIELD_SEC)

            elif state == WorkerState.PAUSED:
                self._wait_for_command()

            elif state in (WorkerState.STOPPED, WorkerState.FAILED):
                break


    def _set_state(self, new_state: WorkerState) -> None:
        with self._state_value.get_lock():
            self._state_value.value = new_state.value

    def _set_last_error(self, message: str) -> None:
        encoded = message.encode("utf-8")[: _LAST_ERROR_ARRAY_SIZE - 1]
        padded = encoded + b"\x00" * (_LAST_ERROR_ARRAY_SIZE - len(encoded))
        with self._last_error_array.get_lock():
            self._last_error_array.raw = padded

    def _increment_tick(self) -> None:
        with self._tick_counter.get_lock():
            self._tick_counter.value += 1

    def _reset_tick(self) -> None:
        with self._tick_counter.get_lock():
            self._tick_counter.value = 0

    def _safe_execute_step(self) -> None:
        """Выполняет один шаг симуляции. При исключении — переход в FAILED."""
        try:
            self._step_fn()
            self._increment_tick()
        except Exception as exc:  # noqa: BLE001
            self._set_last_error(str(exc))
            self._set_state(WorkerState.FAILED)
            self._write_manifest_atomic()

    @property
    def elapsed_simulation_seconds(self) -> float:
        """
        Реальное время симуляции в секундах (только RUNNING-периоды).
        Не растёт в PAUSED/IDLE/STOPPED. Сбрасывается командой RESET.
        """
        since = self._running_since.value
        base = self._elapsed_total.value
        if since > 0.0:
            return base + (time.monotonic() - since)
        return base

    def _start_timer(self) -> None:
        with self._running_since.get_lock():
            self._running_since.value = time.monotonic()

    def _stop_timer(self) -> None:
        """Фиксирует накопленное время и сбрасывает метку старта."""
        with self._running_since.get_lock():
            since = self._running_since.value
            if since > 0.0:
                with self._elapsed_total.get_lock():
                    self._elapsed_total.value += time.monotonic() - since
                self._running_since.value = 0.0

    def _reset_timer(self) -> None:
        with self._running_since.get_lock():
            self._running_since.value = 0.0
        with self._elapsed_total.get_lock():
            self._elapsed_total.value = 0.0

    def _handle_command(self, cmd: WorkerCommand) -> None:
        """Диспетчеризация команд в зависимости от текущего состояния."""
        state = WorkerState(self._state_value.value)

        if cmd == WorkerCommand.START:
            if state in (WorkerState.IDLE, WorkerState.PAUSED):
                self._start_timer()
                self._set_state(WorkerState.RUNNING)

        elif cmd == WorkerCommand.PAUSE:
            if state == WorkerState.RUNNING:
                self._stop_timer()
                self._set_state(WorkerState.PAUSED)

        elif cmd == WorkerCommand.STEP:
            if state == WorkerState.PAUSED:
                # Выполнить ровно один тик и вернуться в PAUSED
                self._safe_execute_step()
                if WorkerState(self._state_value.value) == WorkerState.PAUSED:
                    # Состояние не изменилось step_fn (не упал) — остаёмся в PAUSED
                    pass
                # Если _safe_execute_step перевёл в FAILED — не перезаписываем
            # В RUNNING — игнорируем (не ломаем)

        elif cmd == WorkerCommand.STOP:
            self._stop_timer()
            self._set_state(WorkerState.STOPPED)

        elif cmd == WorkerCommand.RESET:
            self._reset_tick()
            self._reset_timer()
            self._set_last_error("")
            self._set_state(WorkerState.IDLE)

    def _wait_for_command(self) -> None:
        """Блокирующее ожидание команды с таймаутом (не сжигает CPU)."""
        try:
            cmd = self._cmd_queue.get(timeout=_LOOP_CMD_TIMEOUT)
            self._handle_command(cmd)
        except queue.Empty:
            pass

    def _consume_pending_command_non_blocking(self) -> None:
        """Неблокирующая проверка очереди команд в RUNNING-состоянии."""
        try:
            cmd = self._cmd_queue.get_nowait()
            self._handle_command(cmd)
        except queue.Empty:
            pass

    def _write_manifest_atomic(self) -> None:
        """
        Атомарная запись manifest.json через временный файл.
        Гарантирует, что FastAPI никогда не читает полуписанный файл.
        """
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        last_error = self._last_error_array.raw.rstrip(b"\x00").decode("utf-8")
        payload = {
            "state": WorkerState(self._state_value.value).name,
            "last_error": last_error or None,
        }
        tmp_path = self._artifacts_dir / (_MANIFEST_FILENAME + _MANIFEST_TMP_SUFFIX)
        target_path = self._artifacts_dir / _MANIFEST_FILENAME

        tmp_path.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(tmp_path, target_path)


def _worker_entry(
    artifacts_dir: str,
    command_queue: mp.Queue,
    shock_queue: mp.Queue,
    tick_counter: mp.Value,
    state_value: mp.Value,
    last_error_array: mp.Array,
    step_fn_qualname: str | None,
    running_since: mp.Value,
    elapsed_total: mp.Value,
) -> None:
    """
    Функция-мишень для multiprocessing.Process.
    Все аргументы — pickle-safe (строки, примитивы разделяемой памяти).
    """
    if step_fn_qualname is None:
        from market_abm.worker.simulation_session import make_live_step_fn  # noqa: PLC0415

        step_fn = make_live_step_fn(
            artifacts_dir=artifacts_dir,
            shock_queue=shock_queue,
            tick_counter=tick_counter,
        )
    else:
        module_name, func_name = step_fn_qualname.rsplit(".", 1)
        module = importlib.import_module(module_name)
        step_fn = getattr(module, func_name)

    loop = _WorkerLoop(
        command_queue=command_queue,
        tick_counter=tick_counter,
        state_value=state_value,
        last_error_array=last_error_array,
        artifacts_dir=artifacts_dir,
        step_fn=step_fn,
        running_since=running_since,
        elapsed_total=elapsed_total,
    )
    loop.run()


class SimulationWorker:
    """
    Менеджер изолированного процесса симуляции.
    Создаёт subprocess через spawn, экспонирует разделяемое состояние родителю.

    Параметры:
        artifacts_dir: директория для Parquet и manifest.json
        _step_fn_qualname: полный путь к callable для шага (None → production step)

    Pickle Guard: конструктор принимает только строки и примитивы.
    Тяжёлые объекты (DuckDB, CatBoost) создаются внутри subprocess в _worker_entry.
    """

    def __init__(
        self,
        artifacts_dir: str,
        *,
        _step_fn_qualname: str | None = None,
    ) -> None:
        ctx = mp.get_context("spawn")
        self._artifacts_dir = artifacts_dir

        self.command_queue: mp.Queue = ctx.Queue(maxsize=1)
        self.shock_queue: mp.Queue = ctx.Queue(maxsize=_SHOCK_QUEUE_MAXSIZE)
        self.tick_counter: mp.Value = ctx.Value("i", 0)
        self._state_value: mp.Value = ctx.Value("i", WorkerState.IDLE.value)
        self._last_error_array: mp.Array = ctx.Array("c", _LAST_ERROR_ARRAY_SIZE)
        self._running_since: mp.Value = ctx.Value("d", 0.0)
        self._elapsed_total: mp.Value = ctx.Value("d", 0.0)

        self.process: mp.Process = ctx.Process(
            target=_worker_entry,
            args=(
                artifacts_dir,
                self.command_queue,
                self.shock_queue,
                self.tick_counter,
                self._state_value,
                self._last_error_array,
                _step_fn_qualname,
                self._running_since,
                self._elapsed_total,
            ),
            daemon=True,
        )

    @property
    def run_id(self) -> str:
        """run_id из имени каталога артефактов (runs/{run_id})."""
        return Path(self._artifacts_dir).name

    @property
    def state(self) -> WorkerState:
        """Текущее состояние воркера (читается из разделяемой памяти)."""
        return WorkerState(self._state_value.value)

    @property
    def last_error(self) -> str | None:
        """Последняя ошибка воркера или None."""
        with self._last_error_array.get_lock():
            msg = self._last_error_array.raw.rstrip(b"\x00").decode("utf-8")
        return msg if msg else None

    @property
    def elapsed_simulation_seconds(self) -> float:
        """
        Реальное время симуляции в секундах (только RUNNING-периоды).
        Не растёт в PAUSED/IDLE/STOPPED. Сбрасывается командой RESET.
        """
        since = self._running_since.value
        base = self._elapsed_total.value
        if since > 0.0:
            return base + (time.monotonic() - since)
        return base
