# Назначение файла: запись артефактов прогона в Parquet через DuckDB + PyArrow (Slice 004).
# Базовая идея: один тик — два parquet-файла; manifest обновляется атомарно.
from __future__ import annotations

from typing import Final

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl

from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.domain.constants import (
    COL_BUYER_ID,
    COL_PVD_SEGMENT,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    PRODUCTS_COLUMNS,
    SELLERS_STATE_COLUMNS,
    TRANSACTIONS_COLUMNS,
)

_REFERENCE_DIR: Final[str] = "reference"
_REFERENCE_BUYERS_FILE: Final[str] = "buyers.parquet"
_REFERENCE_SELLERS_FILE: Final[str] = "sellers.parquet"


@dataclass(frozen=True, slots=True)
class SimulationRunContext:
    """Идентификатор и корень каталога одного persisted run (не доменный агент)."""

    run_id: str
    run_root: Path


def resolve_run_id(persistence: PersistenceConfig) -> str:
    """Возвращает persistence.run_id или новый uuid4; конфиг не мутируется."""
    if persistence.run_id is not None:
        return persistence.run_id
    return str(uuid.uuid4())


def open_duckdb_connection(persistence: PersistenceConfig) -> duckdb.DuckDBPyConnection:
    """Открывает in-memory DuckDB с лимитом памяти из конфига."""
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{persistence.duckdb_memory_limit}'")
    return con


def _config_hash(config: SimulationRunConfig) -> str:
    payload = config.model_dump(mode="json")
    payload["persistence"]["run_id"] = None
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _validate_frame_columns(df: pl.DataFrame, expected: tuple[str, ...], label: str) -> None:
    # Allow extra columns (e.g. category_id, ranking_score added by Spec 012).
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(
            f"{label} missing required columns: {missing}; present: {df.columns}"
        )


def _tick_path(run_root: Path, subdir: str, tick_id: int) -> Path:
    return run_root / subdir / f"tick_{tick_id:06d}.parquet"


def _write_df_to_parquet_arrow(
    df: pl.DataFrame,
    path: Path,
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Polars → PyArrow → DuckDB COPY; не регистрирует Polars DataFrame напрямую."""
    arrow_table = df.to_arrow()
    rel_name = "_arrow_export"
    con.register(rel_name, arrow_table)
    try:
        con.execute(
            f"COPY (SELECT * FROM {rel_name}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(path)],
        )
    finally:
        con.unregister(rel_name)


def _write_manifest_atomic(run_root: Path, manifest: dict[str, object]) -> None:
    tmp_path = run_root / "manifest.json.tmp"
    final_path = run_root / "manifest.json"
    tmp_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    tmp_path.replace(final_path)


def reference_buyers_path(run_root: Path) -> Path:
    return run_root / _REFERENCE_DIR / _REFERENCE_BUYERS_FILE


def reference_sellers_path(run_root: Path) -> Path:
    return run_root / _REFERENCE_DIR / _REFERENCE_SELLERS_FILE


def write_reference_snapshots(
    run_root: Path,
    *,
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
) -> None:
    """Статические срезы buyers/sellers для demand-matrix (strategy × pvd_segment)."""
    ref_dir = run_root / _REFERENCE_DIR
    ref_dir.mkdir(parents=True, exist_ok=True)

    buyers_df.select(COL_BUYER_ID, COL_PVD_SEGMENT).with_columns(
        pl.col(COL_PVD_SEGMENT).cast(pl.String).alias(COL_PVD_SEGMENT),
    ).write_parquet(reference_buyers_path(run_root))

    sellers_df.select(COL_SELLER_ID, COL_STRATEGY_TYPE).with_columns(
        pl.col(COL_STRATEGY_TYPE).cast(pl.String).alias(COL_STRATEGY_TYPE),
    ).write_parquet(reference_sellers_path(run_root))


def init_run_directory(
    config: SimulationRunConfig,
    *,
    run_id: str,
    buyers_df: pl.DataFrame,
    sellers_df: pl.DataFrame,
    listings_df: pl.DataFrame,
    n_ticks: int,
) -> SimulationRunContext:
    """Создаёт каталог прогона и начальный manifest.json."""
    if n_ticks < 1:
        raise ValueError("n_ticks must be >= 1")

    persistence = config.persistence
    run_root = Path(persistence.base_dir) / run_id
    if run_root.exists():
        raise FileExistsError(f"Run directory already exists: {run_root}")

    (run_root / "transactions").mkdir(parents=True, exist_ok=False)
    (run_root / "products_snapshots").mkdir(parents=False, exist_ok=False)
    (run_root / "sellers_state").mkdir(parents=False, exist_ok=False)
    (run_root / "system_events").mkdir(parents=False, exist_ok=False)
    write_reference_snapshots(run_root, buyers_df=buyers_df, sellers_df=sellers_df)

    manifest: dict[str, object] = {
        "run_id": run_id,
        "created_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_ticks": n_ticks,
        "seed": config.seed,
        "n_buyers": buyers_df.height,
        "n_sellers": sellers_df.height,
        "n_listings": listings_df.height,
        "config_hash": _config_hash(config),
        "engine": config.choice.engine,
        "ticks_completed": 0,
        "last_tick_id": None,
        "paths": {
            "transactions_glob": "transactions/tick_*.parquet",
            "products_glob": "products_snapshots/tick_*.parquet",
            "sellers_state_glob": "sellers_state/tick_*.parquet",
            "system_events_glob": "system_events/evt_*.parquet",
        },
    }
    _write_manifest_atomic(run_root, manifest)
    return SimulationRunContext(run_id=run_id, run_root=run_root)


def persist_tick_artifacts(
    run_root: Path,
    *,
    tick_id: int,
    transactions_df: pl.DataFrame,
    products_df: pl.DataFrame,
    config: PersistenceConfig,
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Пишет transactions и products snapshot тика на диск."""
    _validate_frame_columns(transactions_df, TRANSACTIONS_COLUMNS, "transactions_df")
    _validate_frame_columns(products_df, PRODUCTS_COLUMNS, "products_df")

    path_tx = _tick_path(run_root, "transactions", tick_id)
    path_products = _tick_path(run_root, "products_snapshots", tick_id)
    if path_tx.exists() or path_products.exists():
        raise FileExistsError(f"Tick {tick_id} artifacts already exist under {run_root}")

    path_tx.parent.mkdir(parents=True, exist_ok=True)
    path_products.parent.mkdir(parents=True, exist_ok=True)

    _write_df_to_parquet_arrow(transactions_df, path_tx, con)
    _write_df_to_parquet_arrow(products_df, path_products, con)

    manifest_path = run_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["ticks_completed"] = int(manifest.get("ticks_completed", 0)) + 1
    manifest["last_tick_id"] = tick_id
    _write_manifest_atomic(run_root, manifest)


def persist_sellers_state_snapshot(
    run_root: Path,
    *,
    tick_id: int,
    sellers_state_df: pl.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Пишет sellers_state parquet одного тика."""
    _validate_frame_columns(sellers_state_df, SELLERS_STATE_COLUMNS, "sellers_state_df")
    path = _tick_path(run_root, "sellers_state", tick_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Sellers state snapshot for tick {tick_id} already exists")
    _write_df_to_parquet_arrow(sellers_state_df, path, con)


def clear_run_tick_artifacts(run_root: Path) -> None:
    """Удаляет tick-артефакты прогона (для worker RESET / force_clear)."""
    run_root = Path(run_root)
    for subdir in ("transactions", "products_snapshots", "sellers_state", "system_events"):
        path = run_root / subdir
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def append_drift_alerts(run_root: Path, alerts: list[dict[str, object]]) -> None:
    """Атомарно дописывает записи в manifest['drift_alerts'] (Spec 005 §10.4, опционально)."""
    if not alerts:
        return
    run_root = Path(run_root)
    manifest_path = run_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing = list(manifest.get("drift_alerts", []))
    existing.extend(alerts)
    manifest["drift_alerts"] = existing
    _write_manifest_atomic(run_root, manifest)
