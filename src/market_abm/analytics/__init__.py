# Назначение файла: публичный API аналитического слоя (persistence, позже query).
# Базовая идея: CQRS write-side — Parquet на диске; read-side в AnalyticsStore (4.4).
from market_abm.analytics.persist import (
    SimulationRunContext,
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
    resolve_run_id,
)
from market_abm.analytics.store import AnalyticsStore

__all__ = [
    "AnalyticsStore",
    "SimulationRunContext",
    "init_run_directory",
    "open_duckdb_connection",
    "persist_tick_artifacts",
    "resolve_run_id",
]
