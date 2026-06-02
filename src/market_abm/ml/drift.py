# Назначение файла: мониторинг расслоения признаков ML (Feature Drift, Spec 005 §10).
# Базовая идея: continuous → PSI (квантильные бины ref + epsilon-сглаживание), binary/flag → Jensen-Shannon,
# low-cardinality → SKIPPED, мало строк → DRIFT_UNKNOWN; fail_on_drift падает только на BREACHED.
# Чистые функции над окнами feature_history; без зависимости от CatBoost (CI-путь).
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import polars as pl

from market_abm.config.ml_repricing import DriftMonitorConfig
from market_abm.domain.constants import (
    COL_LISTING_ID,
    COL_SELLER_ID,
    COL_STRATEGY_TYPE,
    COL_TICK_ID,
)


class DriftStatus(str, Enum):
    OK = "ok"
    BREACHED = "breached"
    UNKNOWN = "drift_unknown"  # недостаточно строк
    SKIPPED = "skipped"  # low-cardinality / PSI неприменим


class DriftMetricKind(str, Enum):
    PSI = "psi"
    JENSEN_SHANNON = "jensen_shannon"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Отчёт по одному признаку за тик (Spec 005 §10.3)."""

    as_of_tick: int
    feature_name: str
    status: DriftStatus
    metric_kind: DriftMetricKind
    score: float | None  # PSI или JS; None если UNKNOWN/SKIPPED
    ks_pvalue: float | None  # только continuous PSI path
    n_reference: int
    n_current: int
    n_unique_reference: int


# Не-фичевые колонки (ключи + время); не считаем по ним drift.
_NON_FEATURE_COLUMNS: frozenset[str] = frozenset(
    {COL_TICK_ID, COL_LISTING_ID, COL_SELLER_ID, COL_STRATEGY_TYPE, "run_id"}
)


def drift_reports_to_alerts(reports: list[DriftReport]) -> list[dict[str, object]]:
    """Сериализует отчёты в JSON-совместимые записи для manifest.drift_alerts[] (§10.4)."""
    return [
        {
            "as_of_tick": r.as_of_tick,
            "feature_name": r.feature_name,
            "status": r.status.value,
            "metric_kind": r.metric_kind.value,
            "score": r.score,
            "ks_pvalue": r.ks_pvalue,
            "n_reference": r.n_reference,
            "n_current": r.n_current,
            "n_unique_reference": r.n_unique_reference,
        }
        for r in reports
    ]


def should_check_drift(tick_id: int, config: DriftMonitorConfig) -> bool:
    """Проверять ли drift на данном тике: enabled и tick кратен check_every_n_ticks (§10.4)."""
    if not config.enabled:
        return False
    return tick_id % config.check_every_n_ticks == 0


def compute_feature_drift_report(
    feature_history: pl.DataFrame,
    *,
    config: DriftMonitorConfig,
    as_of_tick: int,
) -> list[DriftReport]:
    """
    Считает drift по каждой фиче между ref- и cur-окнами (Spec 005 §10.3).

    Маршрутизация на признак:
      1) min(n_ref, n_cur) < min_samples_for_drift → UNKNOWN;
      2) n_unique_ref <= 2 или имя ∈ binary_drift_features → Jensen-Shannon;
      3) n_unique_ref <= psi_n_bins → SKIPPED (status OK);
      4) иначе → PSI с epsilon-сглаживанием.
    fail_on_drift=True → ValueError только при наличии BREACHED.
    """
    reference, current = _split_windows(feature_history, config=config, as_of_tick=as_of_tick)
    feature_cols = [c for c in feature_history.columns if c not in _NON_FEATURE_COLUMNS]

    reports: list[DriftReport] = []
    for name in feature_cols:
        reports.append(
            _report_for_feature(
                name,
                reference[name].drop_nulls().to_numpy().astype(np.float64),
                current[name].drop_nulls().to_numpy().astype(np.float64),
                config=config,
                as_of_tick=as_of_tick,
            )
        )

    breached = [r.feature_name for r in reports if r.status == DriftStatus.BREACHED]
    if config.fail_on_drift and breached:
        raise ValueError(f"Feature drift exceeded: {breached}")
    return reports


# --- Внутренние помощники ---


def _split_windows(
    feature_history: pl.DataFrame,
    *,
    config: DriftMonitorConfig,
    as_of_tick: int,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Два смежных окна, заканчивающихся на as_of_tick: ref предшествует cur."""
    cur_lo = as_of_tick - config.current_window_ticks
    ref_lo = cur_lo - config.reference_window_ticks
    reference = feature_history.filter(
        (pl.col(COL_TICK_ID) >= ref_lo) & (pl.col(COL_TICK_ID) < cur_lo)
    )
    current = feature_history.filter(
        (pl.col(COL_TICK_ID) >= cur_lo) & (pl.col(COL_TICK_ID) < as_of_tick)
    )
    return reference, current


def _report_for_feature(
    name: str,
    ref_vals: np.ndarray,
    cur_vals: np.ndarray,
    *,
    config: DriftMonitorConfig,
    as_of_tick: int,
) -> DriftReport:
    n_ref = int(ref_vals.size)
    n_cur = int(cur_vals.size)
    n_unique_ref = int(np.unique(ref_vals).size) if n_ref else 0

    def _report(status: DriftStatus, kind: DriftMetricKind, score: float | None,
                ks_pvalue: float | None) -> DriftReport:
        return DriftReport(
            as_of_tick=as_of_tick,
            feature_name=name,
            status=status,
            metric_kind=kind,
            score=score,
            ks_pvalue=ks_pvalue,
            n_reference=n_ref,
            n_current=n_cur,
            n_unique_reference=n_unique_ref,
        )

    if min(n_ref, n_cur) < config.min_samples_for_drift:
        return _report(DriftStatus.UNKNOWN, DriftMetricKind.SKIPPED, None, None)

    if n_unique_ref <= 2 or name in config.binary_drift_features:
        js = _jensen_shannon_binary(ref_vals, cur_vals)
        status = DriftStatus.BREACHED if js > config.js_threshold else DriftStatus.OK
        return _report(status, DriftMetricKind.JENSEN_SHANNON, js, None)

    if n_unique_ref <= config.psi_n_bins:
        # low-cardinality: PSI неприменим; статус SKIPPED не триггерит fail_on_drift (§10.4).
        return _report(DriftStatus.SKIPPED, DriftMetricKind.SKIPPED, None, None)

    psi = _psi(ref_vals, cur_vals, n_bins=config.psi_n_bins, eps=config.psi_bin_epsilon)
    ks_pvalue = _ks_pvalue(ref_vals, cur_vals)
    status = DriftStatus.BREACHED if psi > config.psi_threshold else DriftStatus.OK
    return _report(status, DriftMetricKind.PSI, psi, ks_pvalue)


def _psi(ref_vals: np.ndarray, cur_vals: np.ndarray, *, n_bins: int, eps: float) -> float:
    """PSI по квантильным бинам ref (§10.2); крайние границы раздвинуты в ±inf."""
    quantile_edges = np.quantile(ref_vals, np.linspace(0.0, 1.0, n_bins + 1))
    quantile_edges[0] = -np.inf
    quantile_edges[-1] = np.inf
    edges = np.unique(quantile_edges)  # дедуп границ при повторных квантилях

    ref_hist = np.histogram(ref_vals, bins=edges)[0].astype(np.float64)
    cur_hist = np.histogram(cur_vals, bins=edges)[0].astype(np.float64)
    p = ref_hist / ref_hist.sum()
    q = cur_hist / cur_hist.sum()
    return float(np.sum((p - q) * np.log((p + eps) / (q + eps))))


def _jensen_shannon_binary(ref_vals: np.ndarray, cur_vals: np.ndarray) -> float:
    """JS-дивергенция на долях события «позитивного» уровня (§10.2)."""
    unique_ref = np.unique(ref_vals)
    positive = 1.0 if 1.0 in unique_ref else (float(unique_ref.max()) if unique_ref.size else 1.0)
    p = float(np.mean(ref_vals == positive))
    q = float(np.mean(cur_vals == positive))
    m = 0.5 * (p + q)
    return 0.5 * _kl_bernoulli(p, m) + 0.5 * _kl_bernoulli(q, m)


def _kl_bernoulli(a: float, b: float) -> float:
    """KL(Bernoulli(a) || Bernoulli(b)) с конвенцией 0*ln(0)=0."""
    total = 0.0
    for ai, bi in ((a, b), (1.0 - a, 1.0 - b)):
        if ai > 0.0 and bi > 0.0:
            total += ai * np.log(ai / bi)
    return float(total)


def _ks_pvalue(ref_vals: np.ndarray, cur_vals: np.ndarray) -> float | None:
    """KS p-value (только continuous PSI path); scipy импортируется лениво."""
    from scipy import stats

    return float(stats.ks_2samp(ref_vals, cur_vals).pvalue)
