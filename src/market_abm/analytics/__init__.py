# Назначение файла: публичный API аналитического слоя (persistence, позже query).
# Базовая идея: CQRS write-side — Parquet на диске; read-side в AnalyticsStore (4.4).
from market_abm.analytics.persist import (
    SimulationRunContext,
    init_run_directory,
    open_duckdb_connection,
    persist_tick_artifacts,
    resolve_run_id,
)

__all__ = [
    "SimulationRunContext",
    "init_run_directory",
    "open_duckdb_connection",
    "persist_tick_artifacts",
    "resolve_run_id",
]
