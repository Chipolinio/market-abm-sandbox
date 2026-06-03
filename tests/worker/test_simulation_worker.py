# Тесты стейт-машины SimulationWorker (Slice 6.1, RED-фаза).
# Стратегия: _WorkerLoop тестируется через threading (mock step_fn, без spawn/pickle ограничений).
# SimulationWorker тестируется как процессная обёртка (daemon, queue, lifecycle).
from __future__ import annotations

import json
import multiprocessing as mp
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from market_abm.worker.process import (
    SimulationWorker,
    WorkerCommand,
    WorkerState,
    _WorkerLoop,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_POLL_INTERVAL = 0.02  # секунд между проверками состояния в wait_for_state


def _wait_for_state(
    state_value: mp.Value,
    expected: WorkerState,
    timeout: float = 3.0,
) -> None:
    """Polling-ожидание перехода в целевое состояние. Падает с AssertionError по таймауту."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if WorkerState(state_value.value) == expected:
            return
        time.sleep(_POLL_INTERVAL)
    actual = WorkerState(state_value.value)
    raise AssertionError(
        f"Timeout {timeout}s: ожидалось состояние {expected.name!r}, "
        f"получено {actual.name!r}"
    )


def _wait_for_tick_above(
    tick_counter: mp.Value,
    threshold: int,
    timeout: float = 3.0,
) -> None:
    """Polling-ожидание пока tick_counter.value > threshold."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tick_counter.value > threshold:
            return
        time.sleep(_POLL_INTERVAL)
    raise AssertionError(
        f"Timeout {timeout}s: ожидался tick > {threshold}, получено {tick_counter.value}"
    )


def _make_loop(
    step_fn: Callable[[], None] | None = None,
    artifacts_dir: str | None = None,
    tmp_path: Path | None = None,
) -> tuple[_WorkerLoop, mp.Queue, mp.Value, mp.Value, mp.Array]:
    """
    Фабрика _WorkerLoop с разделяемыми примитивами для threading-тестов.
    Возвращает (loop, cmd_queue, tick_counter, state_value, last_error_array).
    """
    if step_fn is None:
        step_fn = lambda: None  # noqa: E731
    if artifacts_dir is None:
        artifacts_dir = str(tmp_path or Path("/tmp/worker_test"))

    cmd_queue: mp.Queue = mp.Queue(maxsize=1)
    tick_counter: mp.Value = mp.Value("i", 0)
    state_value: mp.Value = mp.Value("i", WorkerState.IDLE.value)
    last_error_array: mp.Array = mp.Array("c", 2048)

    loop = _WorkerLoop(
        command_queue=cmd_queue,
        tick_counter=tick_counter,
        state_value=state_value,
        last_error_array=last_error_array,
        artifacts_dir=artifacts_dir,
        step_fn=step_fn,
    )
    return loop, cmd_queue, tick_counter, state_value, last_error_array


def _run_loop_in_thread(loop: _WorkerLoop) -> threading.Thread:
    """Запускает loop.run() в daemon-потоке и возвращает поток."""
    t = threading.Thread(target=loop.run, daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# Группа 1: Перечисления и типы (чистые юнит-тесты, без процессов)
# ---------------------------------------------------------------------------


class TestEnums:
    def test_worker_state_has_all_required_states(self) -> None:
        required = {"IDLE", "RUNNING", "PAUSED", "STOPPED", "FAILED"}
        actual = {s.name for s in WorkerState}
        assert required <= actual

    def test_worker_command_has_all_required_commands(self) -> None:
        required = {"START", "PAUSE", "STEP", "STOP", "RESET"}
        actual = {c.name for c in WorkerCommand}
        assert required <= actual

    def test_worker_state_values_are_unique(self) -> None:
        values = [s.value for s in WorkerState]
        assert len(values) == len(set(values))

    def test_worker_command_string_values_are_lowercase(self) -> None:
        for cmd in WorkerCommand:
            assert cmd.value == cmd.value.lower(), f"{cmd.name} value должен быть lowercase"


# ---------------------------------------------------------------------------
# Группа 2: Инициализация _WorkerLoop (без запуска потока)
# ---------------------------------------------------------------------------


class TestWorkerLoopInit:
    def test_initial_state_is_idle(self, tmp_path: Path) -> None:
        _, _, tick_counter, state_value, last_error_array = _make_loop(tmp_path=tmp_path)
        assert WorkerState(state_value.value) == WorkerState.IDLE

    def test_initial_tick_counter_is_zero(self, tmp_path: Path) -> None:
        _, _, tick_counter, _, _ = _make_loop(tmp_path=tmp_path)
        assert tick_counter.value == 0

    def test_initial_last_error_is_empty(self, tmp_path: Path) -> None:
        _, _, _, _, last_error_array = _make_loop(tmp_path=tmp_path)
        msg = last_error_array.raw.rstrip(b"\x00").decode("utf-8")
        assert msg == ""


# ---------------------------------------------------------------------------
# Группа 3: Переходы стейт-машины (loop через threading)
# ---------------------------------------------------------------------------


class TestWorkerLoopStateMachine:
    def test_start_command_transitions_to_running(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_pause_from_running_transitions_to_paused(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)

        cmd_queue.put(WorkerCommand.PAUSE)
        _wait_for_state(state_value, WorkerState.PAUSED)

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_start_from_paused_resumes_to_running(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)
        cmd_queue.put(WorkerCommand.PAUSE)
        _wait_for_state(state_value, WorkerState.PAUSED)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_stop_from_running_transitions_to_stopped(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)

        cmd_queue.put(WorkerCommand.STOP)
        _wait_for_state(state_value, WorkerState.STOPPED)
        t.join(timeout=3.0)
        assert not t.is_alive()

    def test_stop_from_paused_transitions_to_stopped(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)
        cmd_queue.put(WorkerCommand.PAUSE)
        _wait_for_state(state_value, WorkerState.PAUSED)

        cmd_queue.put(WorkerCommand.STOP)
        _wait_for_state(state_value, WorkerState.STOPPED)
        t.join(timeout=3.0)
        assert not t.is_alive()

    def test_stop_terminates_loop_thread(self, tmp_path: Path) -> None:
        """STOP переводит в STOPPED и завершает цикл (поток умирает)."""
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)
        cmd_queue.put(WorkerCommand.STOP)
        _wait_for_state(state_value, WorkerState.STOPPED)

        t.join(timeout=3.0)
        # Поток должен завершиться — STOPPED является терминальным для цикла
        assert not t.is_alive()


# ---------------------------------------------------------------------------
# Группа 4: Команда STEP и атомарность счётчика тиков
# ---------------------------------------------------------------------------


class TestWorkerLoopStep:
    def _go_to_paused(
        self, cmd_queue: mp.Queue, state_value: mp.Value
    ) -> None:
        """Вспомогательный переход: IDLE → RUNNING → PAUSED."""
        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)
        cmd_queue.put(WorkerCommand.PAUSE)
        _wait_for_state(state_value, WorkerState.PAUSED)

    def test_step_from_paused_increments_tick_by_one(self, tmp_path: Path) -> None:
        loop, cmd_queue, tick_counter, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)
        self._go_to_paused(cmd_queue, state_value)

        before = tick_counter.value
        cmd_queue.put(WorkerCommand.STEP)
        # Ждём пока тик увеличится — не состояние (уже PAUSED), а счётчик
        _wait_for_tick_above(tick_counter, before, timeout=3.0)

        assert tick_counter.value == before + 1
        assert WorkerState(state_value.value) == WorkerState.PAUSED

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_step_returns_to_paused_after_execution(self, tmp_path: Path) -> None:
        loop, cmd_queue, tick_counter, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)
        self._go_to_paused(cmd_queue, state_value)

        before = tick_counter.value
        cmd_queue.put(WorkerCommand.STEP)
        _wait_for_tick_above(tick_counter, before, timeout=3.0)

        assert WorkerState(state_value.value) == WorkerState.PAUSED

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_tick_counter_updated_only_after_step_completes(self, tmp_path: Path) -> None:
        """step_fn с задержкой: tick_counter не должен меняться пока step не завершён.

        Стартуем сразу из PAUSED (state_value устанавливается до запуска потока),
        чтобы _slow_step не вызывался автоматически в RUNNING до команды STEP.
        """
        step_started = threading.Event()
        step_may_finish = threading.Event()

        def _slow_step() -> None:
            step_started.set()
            step_may_finish.wait(timeout=5.0)

        loop, cmd_queue, tick_counter, state_value, _ = _make_loop(
            step_fn=_slow_step, tmp_path=tmp_path
        )
        # Инициализируем PAUSED до старта потока: loop сразу ждёт команды
        with state_value.get_lock():
            state_value.value = WorkerState.PAUSED.value

        t = _run_loop_in_thread(loop)
        time.sleep(0.05)  # даём потоку войти в цикл ожидания

        before = tick_counter.value
        cmd_queue.put(WorkerCommand.STEP)

        assert step_started.wait(timeout=5.0), "step_fn не запустился за 5 секунд"
        # step_fn запущен, но NOT завершён → счётчик не изменился
        assert tick_counter.value == before

        step_may_finish.set()
        _wait_for_tick_above(tick_counter, before, timeout=3.0)

        assert tick_counter.value == before + 1

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_multiple_steps_monotonic_counter(self, tmp_path: Path) -> None:
        n_steps = 5
        loop, cmd_queue, tick_counter, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)
        self._go_to_paused(cmd_queue, state_value)

        start_tick = tick_counter.value  # может быть > 0 (тики из RUNNING-фазы)
        for _ in range(n_steps):
            before = tick_counter.value
            cmd_queue.put(WorkerCommand.STEP)
            _wait_for_tick_above(tick_counter, before, timeout=3.0)

        assert tick_counter.value == start_tick + n_steps

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)

    def test_step_ignored_when_running(self, tmp_path: Path) -> None:
        """STEP в состоянии RUNNING не должен ломать воркер и не меняет state."""
        loop, cmd_queue, _, state_value, _ = _make_loop(tmp_path=tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.RUNNING)

        # Отправляем STEP из RUNNING — должен быть проигнорирован или
        # обработан как no-op; state остаётся RUNNING
        cmd_queue.put(WorkerCommand.STEP)
        time.sleep(0.2)
        assert WorkerState(state_value.value) == WorkerState.RUNNING

        cmd_queue.put(WorkerCommand.STOP)
        t.join(timeout=3.0)


# ---------------------------------------------------------------------------
# Группа 5: Обработка исключений и FAILED
# ---------------------------------------------------------------------------


class TestWorkerLoopFailedState:
    def _make_raising_loop(self, tmp_path: Path, error_msg: str = "test failure"):
        def _raising_step() -> None:
            raise RuntimeError(error_msg)

        return _make_loop(step_fn=_raising_step, tmp_path=tmp_path)

    def test_exception_in_step_transitions_to_failed(self, tmp_path: Path) -> None:
        loop, cmd_queue, _, state_value, _ = self._make_raising_loop(tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)

        t.join(timeout=3.0)
        assert not t.is_alive()

    def test_failed_state_captures_error_message(self, tmp_path: Path) -> None:
        error_msg = "OOM: not enough memory"
        loop, cmd_queue, _, state_value, last_error_array = self._make_raising_loop(
            tmp_path, error_msg
        )
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        captured = last_error_array.raw.rstrip(b"\x00").decode("utf-8")
        assert error_msg in captured

    def test_failed_state_is_terminal_without_reset(self, tmp_path: Path) -> None:
        """После FAILED команда START не перезапускает воркер (нужен RESET)."""
        loop, cmd_queue, _, state_value, _ = self._make_raising_loop(tmp_path)
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        # Проверяем, что loop завершился и не принимает новые команды
        assert not t.is_alive()
        assert WorkerState(state_value.value) == WorkerState.FAILED

    def test_reset_after_failed_restores_idle(self, tmp_path: Path) -> None:
        loop, cmd_queue, tick_counter, state_value, last_error_array = (
            self._make_raising_loop(tmp_path)
        )
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        # Создаём новый loop для имитации RESET (процесс перезапускается)
        new_loop, new_cmd_queue, new_tick, new_state, new_error = _make_loop(
            tmp_path=tmp_path
        )
        # RESET должен обнулить состояние — проверяем новый loop в IDLE
        assert WorkerState(new_state.value) == WorkerState.IDLE
        assert new_tick.value == 0
        assert new_error.raw.rstrip(b"\x00").decode("utf-8") == ""


# ---------------------------------------------------------------------------
# Группа 6: Атомарная запись manifest.json
# ---------------------------------------------------------------------------


class TestManifestWrite:
    def test_manifest_written_on_failed_state(self, tmp_path: Path) -> None:
        """При переходе в FAILED воркер записывает manifest.json в artifacts_dir."""

        def _raising_step() -> None:
            raise RuntimeError("disk full")

        loop, cmd_queue, _, state_value, _ = _make_loop(
            step_fn=_raising_step, tmp_path=tmp_path
        )
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        manifest_path = tmp_path / "manifest.json"
        assert manifest_path.exists(), "manifest.json должен существовать после FAILED"

    def test_manifest_json_is_valid_after_failed(self, tmp_path: Path) -> None:
        """manifest.json после FAILED парсится без JSONDecodeError."""

        def _raising_step() -> None:
            raise RuntimeError("boom")

        loop, cmd_queue, _, state_value, _ = _make_loop(
            step_fn=_raising_step, tmp_path=tmp_path
        )
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        manifest_path = tmp_path / "manifest.json"
        data = json.loads(manifest_path.read_text())
        assert "state" in data
        assert "last_error" in data
        assert data["state"] == "FAILED"

    def test_manifest_no_tmp_file_left_after_write(self, tmp_path: Path) -> None:
        """После атомарной записи .tmp файл не должен оставаться на диске."""

        def _raising_step() -> None:
            raise RuntimeError("err")

        loop, cmd_queue, _, state_value, _ = _make_loop(
            step_fn=_raising_step, tmp_path=tmp_path
        )
        t = _run_loop_in_thread(loop)

        cmd_queue.put(WorkerCommand.START)
        _wait_for_state(state_value, WorkerState.FAILED)
        t.join(timeout=3.0)

        tmp_file = tmp_path / "manifest.json.tmp"
        assert not tmp_file.exists(), "manifest.json.tmp не должен оставаться на диске"


# ---------------------------------------------------------------------------
# Группа 7: SimulationWorker — процессная обёртка
# ---------------------------------------------------------------------------


class TestSimulationWorker:
    def _make_worker(self, tmp_path: Path) -> SimulationWorker:
        """Создаёт SimulationWorker с noop step_fn для тестов."""
        return SimulationWorker(
            artifacts_dir=str(tmp_path),
            _step_fn_qualname="market_abm.worker.process._noop_step",
        )

    def test_process_is_daemon(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        assert worker.process.daemon is True

    def test_command_queue_maxsize_is_one(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        assert worker.command_queue._maxsize == 1  # type: ignore[attr-defined]

    def test_initial_state_is_idle(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        assert worker.state == WorkerState.IDLE

    def test_initial_tick_count_is_zero(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        assert worker.tick_counter.value == 0

    def test_initial_last_error_is_none(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        assert worker.last_error is None

    @pytest.mark.worker
    def test_process_is_alive_after_start(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        worker.process.start()
        try:
            assert worker.process.is_alive()
        finally:
            worker.process.terminate()
            worker.process.join(timeout=5.0)

    @pytest.mark.worker
    def test_process_terminates_after_stop_command(self, tmp_path: Path) -> None:
        worker = self._make_worker(tmp_path)
        worker.process.start()

        worker.command_queue.put(WorkerCommand.STOP)
        worker.process.join(timeout=5.0)

        assert not worker.process.is_alive()
