# Статическая проверка README для слайса 7.6 (Docker/volume документация).
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README = _REPO_ROOT / "README.md"


def test_readme_exists() -> None:
    assert _README.is_file()


def test_readme_documents_docker_operations() -> None:
    text = _README.read_text(encoding="utf-8")
    required = [
        "docker compose up",
        "localhost:3000",
        "localhost:8000",
        "docker compose down",
        "down -v",
        "docker-compose.dev.yml",
        "ENABLE_CORS=1",
        "market_abm_runs",
    ]
    for fragment in required:
        assert fragment in text, f"README missing: {fragment}"
