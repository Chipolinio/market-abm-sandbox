# Назначение файла: legacy/bootstrap колонки buyers_df (Spec 010 §10.1, Spec 011 §7.1).
# Базовая идея: no-op если колонки есть; иначе alias из budget / purchase_frequency.
from __future__ import annotations

import polars as pl

from market_abm.domain.constants import (
    COL_BUDGET,
    COL_BUDGET_BASELINE,
    COL_BUDGET_EFFECTIVE,
    COL_FREQ_BASELINE,
    COL_FREQ_EFFECTIVE,
    COL_IS_CHURNED,
    COL_PURCHASE_FREQUENCY,
    COL_SCAR_FACTOR,
)


def ensure_budget_baseline(buyers_df: pl.DataFrame) -> pl.DataFrame:
    """Добавляет budget_baseline из budget, если колонка отсутствует."""
    if COL_BUDGET_BASELINE in buyers_df.columns:
        return buyers_df
    return buyers_df.with_columns(pl.col(COL_BUDGET).alias(COL_BUDGET_BASELINE))


def ensure_buyer_economic_columns(buyers_df: pl.DataFrame) -> pl.DataFrame:
    """Добавляет macro/economic runtime-колонки для legacy frames без полной схемы 011."""
    df = ensure_budget_baseline(buyers_df)
    if COL_FREQ_BASELINE not in df.columns:
        freq_src = (
            COL_PURCHASE_FREQUENCY
            if COL_PURCHASE_FREQUENCY in df.columns
            else COL_BUDGET
        )
        df = df.with_columns(pl.col(freq_src).cast(pl.Float32).alias(COL_FREQ_BASELINE))
    if COL_BUDGET_EFFECTIVE not in df.columns:
        budget_src = COL_BUDGET if COL_BUDGET in df.columns else COL_BUDGET_BASELINE
        df = df.with_columns(pl.col(budget_src).cast(pl.Float32).alias(COL_BUDGET_EFFECTIVE))
    if COL_FREQ_EFFECTIVE not in df.columns:
        df = df.with_columns(pl.col(COL_FREQ_BASELINE).alias(COL_FREQ_EFFECTIVE))
    if COL_SCAR_FACTOR not in df.columns:
        df = df.with_columns(pl.lit(0.0, dtype=pl.Float32).alias(COL_SCAR_FACTOR))
    if COL_IS_CHURNED not in df.columns:
        df = df.with_columns(pl.lit(False).alias(COL_IS_CHURNED))
    return df
