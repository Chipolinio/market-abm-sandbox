# Shared fixtures/helpers for worker session tests (Slice A.1).
from __future__ import annotations

import json
from pathlib import Path


def write_pending_session(run_root: Path, payload: dict[str, object]) -> None:
    """Записывает pending_session.json — контракт POST /configure + POST /start merge."""
    run_root.mkdir(parents=True, exist_ok=True)
    path = run_root / "pending_session.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def read_manifest(run_root: Path) -> dict[str, object]:
    return json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
