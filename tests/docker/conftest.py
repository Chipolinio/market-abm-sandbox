# Фикстуры Docker Compose smoke (Spec 007 §7.5).
from __future__ import annotations

import uuid
from collections.abc import Generator

import pytest

from tests.docker.compose_support import (
    ComposeSession,
    docker_daemon_available,
    wait_healthy,
)


@pytest.fixture(scope="module")
def compose_session() -> Generator[ComposeSession, None, None]:
    if not docker_daemon_available():
        pytest.skip("Docker daemon not available")

    session = ComposeSession(project=f"market_abm_pytest_{uuid.uuid4().hex[:8]}")

    build = session.run("build", timeout=600)
    assert build.returncode == 0, build.stderr

    up = session.run("up", "-d", "--wait", timeout=300)
    assert up.returncode == 0, up.stderr or up.stdout

    try:
        wait_healthy()
        yield session
    finally:
        down = session.run("down", "-v", timeout=120)
        if down.returncode != 0:
            pytest.fail(f"compose down failed: {down.stderr}")


@pytest.fixture(scope="module")
def compose_stack(compose_session: ComposeSession) -> ComposeSession:
    return compose_session
