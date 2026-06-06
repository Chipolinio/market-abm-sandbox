# Назначение файла: хелперы Docker Compose smoke (без pytest-фикстур).
# Базовая идея: импортируется из conftest и test-модулей; conftest не импортируется напрямую.
from __future__ import annotations

import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import urllib.error
import urllib.request

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_DIR = _REPO_ROOT / "docker"
_COMPOSE_BASE = _COMPOSE_DIR / "docker-compose.yml"
_COMPOSE_TEST = _COMPOSE_DIR / "docker-compose.test.yml"
API_BASE = "http://localhost:18000"
FRONTEND_BASE = "http://localhost:13000"


@dataclass
class ComposeSession:
    project: str

    @property
    def backend_container(self) -> str:
        return "market_abm_backend_pytest"

    def cmd(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "-f",
            str(_COMPOSE_BASE),
            "-f",
            str(_COMPOSE_TEST),
            "-p",
            self.project,
            *args,
        ]

    def run(self, *args: str, timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            self.cmd(*args),
            cwd=_COMPOSE_DIR,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )


def docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def http_get(url: str, *, timeout: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def http_post(url: str, *, body: dict | None = None, timeout: float = 10.0) -> tuple[int, str]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


def wait_healthy(*, timeout_sec: float = 120.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, body = http_get(f"{API_BASE}/api/v1/health")
            if status == 200 and '"status"' in body and "ok" in body:
                return
        except (urllib.error.URLError, ConnectionResetError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(1.0)
    msg = "backend health check timed out"
    if last_error is not None:
        raise TimeoutError(msg) from last_error
    raise TimeoutError(msg)


def stop_and_reset_simulation() -> None:
    """PAUSE (если RUNNING) → RESET: освобождает DuckDB/Parquet перед wipe volume."""
    status, body = http_get(f"{API_BASE}/api/v1/simulation/status")
    if status == 200:
        payload = json.loads(body)
        if payload.get("state") == "RUNNING":
            http_post(f"{API_BASE}/api/v1/simulation/pause")
            time.sleep(0.5)
    http_post(f"{API_BASE}/api/v1/simulation/reset")
    time.sleep(1.0)


def wait_tick_at_least(min_tick: int, *, timeout_sec: float = 30.0) -> int:
    deadline = time.monotonic() + timeout_sec
    last_payload: dict | None = None
    while time.monotonic() < deadline:
        status, body = http_get(f"{API_BASE}/api/v1/simulation/status")
        if status == 200:
            payload = json.loads(body)
            last_payload = payload
            if payload.get("state") == "FAILED":
                err = payload.get("last_error") or "unknown"
                raise AssertionError(f"worker FAILED before tick {min_tick}: {err}")
            tick = int(payload["current_tick"])
            if tick >= min_tick:
                return tick
        time.sleep(0.5)
    detail = ""
    if last_payload is not None:
        detail = (
            f" last_state={last_payload.get('state')!r}"
            f" current_tick={last_payload.get('current_tick')}"
            f" last_error={last_payload.get('last_error')!r}"
        )
    raise TimeoutError(f"current_tick did not reach {min_tick}.{detail}")


def wait_container_file(
    session: ComposeSession,
    path: str,
    *,
    timeout_sec: float = 120.0,
) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = docker_exec(session, "test", "-f", path)
        if result.returncode == 0:
            return
        time.sleep(1.0)
    raise TimeoutError(f"file not found in container: {path}")


def docker_exec(
    session: ComposeSession,
    *args: str,
    user: str | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "exec"]
    if user is not None:
        cmd.extend(["-u", user])
    cmd.append(session.backend_container)
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def seed_volume_from_host(session: ComposeSession, run_root: Path) -> None:
    """Копирует mini_run в /data/runs/ внутри backend-контейнера."""
    parent = run_root.parent
    result = subprocess.run(
        [
            "docker",
            "cp",
            f"{parent}/.",
            f"{session.backend_container}:/data/runs/",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
