# Валидация Docker Compose манифеста (Spec 007 §10.3, слайс 7.4).
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE_DIR = _REPO_ROOT / "docker"
_COMPOSE_FILE = _COMPOSE_DIR / "docker-compose.yml"


def _docker_daemon_available() -> bool:
    if shutil.which("docker") is None:
        return False
    probe = subprocess.run(
        ["docker", "info"],
        capture_output=True,
        text=True,
        check=False,
    )
    return probe.returncode == 0


def _run_compose_config(*extra_files: str) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "compose", "-f", str(_COMPOSE_FILE), *extra_files, "config"]
    return subprocess.run(
        cmd,
        cwd=_COMPOSE_DIR,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.docker
def test_compose_config_valid() -> None:
    if not _docker_daemon_available():
        pytest.skip("Docker daemon not available")
    """7.3-T1: docker compose config exit 0."""
    result = _run_compose_config()
    assert result.returncode == 0, result.stderr
    assert "market_abm_backend" in result.stdout
    assert "market_abm_frontend" in result.stdout
    assert "market_abm_runs" in result.stdout


@pytest.mark.docker
def test_compose_dev_override_valid() -> None:
    if not _docker_daemon_available():
        pytest.skip("Docker daemon not available")
    dev_file = _COMPOSE_DIR / "docker-compose.dev.yml"
    result = _run_compose_config("-f", str(dev_file))
    assert result.returncode == 0, result.stderr


@pytest.mark.docker
def test_frontend_depends_on_backend_health() -> None:
    if not _docker_daemon_available():
        pytest.skip("Docker daemon not available")
    result = _run_compose_config()
    assert result.returncode == 0, result.stderr
    assert "condition: service_healthy" in result.stdout


@pytest.mark.docker
def test_backend_healthcheck_uses_curl() -> None:
    if not _docker_daemon_available():
        pytest.skip("Docker daemon not available")
    result = _run_compose_config()
    assert result.returncode == 0, result.stderr
    assert "/api/v1/health" in result.stdout


def test_docker_artifacts_exist() -> None:
    """Статическая проверка без docker daemon."""
    assert (_COMPOSE_DIR / "backend" / "Dockerfile").is_file()
    assert (_COMPOSE_DIR / "frontend" / "Dockerfile").is_file()
    assert (_COMPOSE_DIR / "frontend" / "nginx.conf").is_file()
