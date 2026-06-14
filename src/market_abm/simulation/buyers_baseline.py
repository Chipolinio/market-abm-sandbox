# Назначение файла: budget_baseline для legacy buyers_df без колонки (Spec 010 §10.1).
# Базовая идея: no-op если колонка есть; иначе alias budget → budget_baseline.
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import COL_BUDGET, COL_BUDGET_BASELINE


def ensure_budget_baseline(buyers_df: pl.DataFrame) -> pl.DataFrame:
    """Добавляет budget_baseline из budget, если колонка отсутствует."""
    if COL_BUDGET_BASELINE in buyers_df.columns:
        return buyers_df
    return buyers_df.with_columns(pl.col(COL_BUDGET).alias(COL_BUDGET_BASELINE))
