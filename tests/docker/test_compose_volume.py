# Volume persistence smoke (Spec 007 §10.3, слайс 7.5).
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from tests.docker.compose_support import (
    API_BASE,
    FRONTEND_BASE,
    ComposeSession,
    docker_exec,
    http_get,
    http_post,
    seed_volume_from_host,
    stop_and_reset_simulation,
    wait_container_file,
    wait_healthy,
    wait_tick_at_least,
)
from tests.helpers.mini_run import build_mini_run

pytestmark = pytest.mark.docker

_TICK0_PARQUET = "/data/runs/default/transactions/tick_000000.parquet"


def test_volume_mount_exists_in_backend_container(compose_stack: ComposeSession) -> None:
    result = docker_exec(compose_stack, "test", "-d", "/data/runs")
    assert result.returncode == 0, result.stderr


def test_nginx_proxies_api_on_test_ports(compose_stack: ComposeSession) -> None:
    status, body = http_get(f"{FRONTEND_BASE}/api/v1/simulation/status")
    assert status == 200
    assert '"state"' in body


def test_appuser_can_write_to_volume(compose_stack: ComposeSession) -> None:
    mkdir = docker_exec(compose_stack, "mkdir", "-p", "/data/runs/default", user="appuser")
    assert mkdir.returncode == 0, mkdir.stderr

    probe = "/data/runs/default/.write_probe"
    touch = docker_exec(compose_stack, "touch", probe, user="appuser")
    assert touch.returncode == 0, touch.stderr

    restart = compose_stack.run("restart", "market_abm_backend", timeout=120)
    assert restart.returncode == 0, restart.stderr
    wait_healthy()

    exists = docker_exec(compose_stack, "test", "-f", probe)
    assert exists.returncode == 0, exists.stderr


def test_start_simulation_worker_not_failed_in_live_mode(compose_stack: ComposeSession) -> None:
    """Live step (Spec 008): воркер не падает, тики наращиваются."""
    status_code, _ = http_post(f"{API_BASE}/api/v1/simulation/start")
    assert status_code == 202

    wait_tick_at_least(1, timeout_sec=180)
    wait_container_file(compose_stack, _TICK0_PARQUET, timeout_sec=30)

    _, body = http_get(f"{API_BASE}/api/v1/simulation/status")
    payload = json.loads(body)
    assert payload["state"] == "RUNNING"
    assert payload.get("last_error") in (None, "")

    stop_and_reset_simulation()


def test_backend_restart_preserves_seeded_parquet(compose_stack: ComposeSession) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp), run_id="default")
        assert (run_root / "transactions" / "tick_000000.parquet").is_file()
        seed_volume_from_host(compose_stack, run_root)

    restart = compose_stack.run("restart", "market_abm_backend", timeout=120)
    assert restart.returncode == 0, restart.stderr
    wait_healthy()

    exists = docker_exec(compose_stack, "test", "-f", _TICK0_PARQUET)
    assert exists.returncode == 0, exists.stderr


def test_analytics_price_index_after_restart_with_seeded_data(compose_stack: ComposeSession) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp), run_id="default")
        seed_volume_from_host(compose_stack, run_root)

    restart = compose_stack.run("restart", "market_abm_backend", timeout=120)
    assert restart.returncode == 0, restart.stderr
    wait_healthy()

    _, body = http_get(f"{API_BASE}/api/v1/analytics/price-index")
    payload = json.loads(body)
    points = payload["points"]
    assert len(points) > 0
    tick_ids = [p["tick_id"] for p in points]
    assert tick_ids == sorted(tick_ids)


def _wipe_run_artifacts(session: ComposeSession) -> None:
    """Сброс named volume (Docker Desktop Mac: rm/chown внутри контейнера ненадёжны)."""
    stop_and_reset_simulation()

    down = session.run("down", "-v", timeout=180)
    assert down.returncode == 0, down.stderr

    up = session.run("up", "-d", "--wait", timeout=300)
    assert up.returncode == 0, up.stderr or up.stdout
    wait_healthy()


def test_volume_writable_creates_parquet_on_tick_1(compose_stack: ComposeSession) -> None:
    """7.3-T7: полный контракт — после START появляется tick_0.parquet."""
    _wipe_run_artifacts(compose_stack)

    http_post(f"{API_BASE}/api/v1/simulation/start")
    wait_container_file(compose_stack, _TICK0_PARQUET, timeout_sec=180)

    _, body = http_get(f"{API_BASE}/api/v1/simulation/status")
    payload = json.loads(body)
    assert payload["state"] != "FAILED"


def test_volume_survives_backend_restart_via_live_simulation(compose_stack: ComposeSession) -> None:
    """7.3-T6: START → ticks → restart → price-index > 0 без seed."""
    _wipe_run_artifacts(compose_stack)

    http_post(f"{API_BASE}/api/v1/simulation/start")
    wait_tick_at_least(3, timeout_sec=180)

    restart = compose_stack.run("restart", "market_abm_backend", timeout=120)
    assert restart.returncode == 0, restart.stderr
    wait_healthy()

    _, body = http_get(f"{API_BASE}/api/v1/analytics/price-index")
    payload = json.loads(body)
    assert len(payload["points"]) > 0


def test_down_without_v_preserves_named_volume(compose_stack: ComposeSession) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp), run_id="default")
        seed_volume_from_host(compose_stack, run_root)

    down = compose_stack.run("down", timeout=120)
    assert down.returncode == 0, down.stderr

    up = compose_stack.run("up", "-d", "--wait", timeout=300)
    assert up.returncode == 0, up.stderr or up.stdout
    wait_healthy()

    _, body = http_get(f"{API_BASE}/api/v1/analytics/price-index")
    payload = json.loads(body)
    assert len(payload["points"]) > 0


def test_down_with_v_clears_analytics(compose_stack: ComposeSession) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_root = build_mini_run(Path(tmp), run_id="default")
        seed_volume_from_host(compose_stack, run_root)

    down = compose_stack.run("down", "-v", timeout=120)
    assert down.returncode == 0, down.stderr

    up = compose_stack.run("up", "-d", "--wait", timeout=300)
    assert up.returncode == 0, up.stderr or up.stdout
    wait_healthy()

    _, body = http_get(f"{API_BASE}/api/v1/analytics/price-index")
    payload = json.loads(body)
    assert payload["points"] == []
