# Назначение файла: RED-тесты слайса 5.6 — Feature Drift (PSI/JS, UNKNOWN/SKIPPED) (Spec 005 §10, §12.7).
# Базовая идея: continuous → PSI (квантильные бины ref), binary/flag → Jensen-Shannon, low-card → SKIPPED,
# мало строк → DRIFT_UNKNOWN; fail_on_drift=True падает только на BREACHED.
from __future__ import annotations

import numpy as np
import polars as pl
import pytest

from market_abm.config.ml_repricing import DriftMonitorConfig
from market_abm.domain.constants import COL_TICK_ID

# --- SUT (ещё не существует → RED на импорте) ---
from market_abm.ml.drift import (
    DriftMetricKind,
    DriftReport,
    DriftStatus,
    compute_feature_drift_report,
    should_check_drift,
)

_REF_TICK = 10
_CUR_TICK = 30
_AS_OF = 40


def _drift_config(**overrides: object) -> DriftMonitorConfig:
    base: dict[str, object] = dict(
        reference_window_ticks=20,
        current_window_ticks=20,
        min_samples_for_drift=500,
    )
    base.update(overrides)
    return DriftMonitorConfig(**base)


def _history(
    ref_vals: np.ndarray, cur_vals: np.ndarray, *, name: str
) -> pl.DataFrame:
    """Двухоконная история: ref-строки в [0,20), cur-строки в [20,40) (см. _AS_OF)."""
    ref = pl.DataFrame(
        {COL_TICK_ID: [_REF_TICK] * ref_vals.shape[0], name: ref_vals.astype(np.float64)}
    )
    cur = pl.DataFrame(
        {COL_TICK_ID: [_CUR_TICK] * cur_vals.shape[0], name: cur_vals.astype(np.float64)}
    )
    return pl.concat([ref, cur]).with_columns(pl.col(COL_TICK_ID).cast(pl.Int32))


def _by_name(reports: list[DriftReport], name: str) -> DriftReport:
    return next(r for r in reports if r.feature_name == name)


# --- 5.6-T1 ---


def test_psi_identical_distributions_near_zero() -> None:
    rng = np.random.default_rng(0)
    vals = rng.normal(0.0, 1.0, 600)
    history = _history(vals, vals.copy(), name="roll_mean_price_listing_5")
    reports = compute_feature_drift_report(
        history, config=_drift_config(), as_of_tick=_AS_OF
    )
    report = _by_name(reports, "roll_mean_price_listing_5")
    assert report.metric_kind == DriftMetricKind.PSI
    assert report.score is not None and report.score < 0.01
    assert report.status == DriftStatus.OK


# --- 5.6-T2 ---


def test_psi_detects_shifted_distribution() -> None:
    rng = np.random.default_rng(1)
    ref = rng.normal(0.0, 1.0, 600)
    cur = rng.normal(3.0, 1.0, 600)  # сдвиг среднего
    history = _history(ref, cur, name="roll_mean_price_listing_5")
    config = _drift_config(psi_threshold=0.25)
    reports = compute_feature_drift_report(history, config=config, as_of_tick=_AS_OF)
    report = _by_name(reports, "roll_mean_price_listing_5")
    assert report.metric_kind == DriftMetricKind.PSI
    assert report.score is not None and report.score > config.psi_threshold
    assert report.status == DriftStatus.BREACHED


# --- 5.6-T3 ---


def test_fail_on_drift_raises() -> None:
    rng = np.random.default_rng(2)
    ref = rng.normal(0.0, 1.0, 600)
    cur = rng.normal(3.0, 1.0, 600)
    history = _history(ref, cur, name="roll_mean_price_listing_5")
    config = _drift_config(fail_on_drift=True)
    with pytest.raises(ValueError):
        compute_feature_drift_report(history, config=config, as_of_tick=_AS_OF)


# --- 5.6-T4 ---


def test_drift_check_every_n_ticks() -> None:
    config = _drift_config(check_every_n_ticks=10)
    fired = [t for t in range(0, 35) if should_check_drift(t, config)]
    assert fired == [0, 10, 20, 30]
    # выключенный монитор не запускает проверку даже на кратном тике
    assert not should_check_drift(
        20, _drift_config(check_every_n_ticks=10, enabled=False)
    )


# --- 5.6-T5 (long-run, slow + ml) ---


@pytest.mark.slow
@pytest.mark.ml
def test_hundred_twenty_ticks_drift_alert_slow() -> None:
    rng = np.random.default_rng(5)
    name = "competitor_price_gap"
    n_per_tick = 30
    rows: list[pl.DataFrame] = []
    for tick in range(120):
        shift = 0.0 if tick < 60 else 4.0  # injection shift после тика 60
        vals = rng.normal(shift, 1.0, n_per_tick)
        rows.append(
            pl.DataFrame({COL_TICK_ID: [tick] * n_per_tick, name: vals})
        )
    history = pl.concat(rows).with_columns(pl.col(COL_TICK_ID).cast(pl.Int32))

    config = _drift_config(check_every_n_ticks=10)
    # as_of=80: ref [40,60) до сдвига, cur [60,80) после сдвига → BREACHED
    reports = compute_feature_drift_report(history, config=config, as_of_tick=80)
    report = _by_name(reports, name)
    assert report.metric_kind == DriftMetricKind.PSI
    assert report.status == DriftStatus.BREACHED
    assert report.n_reference >= config.min_samples_for_drift


# --- 5.6-T6 ---


def test_drift_unknown_on_small_sample_no_fail() -> None:
    rng = np.random.default_rng(6)
    ref = rng.normal(0.0, 1.0, 40)
    cur = rng.normal(3.0, 1.0, 40)  # был бы breach, но строк мало
    history = _history(ref, cur, name="roll_mean_price_listing_5")
    config = _drift_config(fail_on_drift=True)  # не должно упасть на UNKNOWN
    reports = compute_feature_drift_report(history, config=config, as_of_tick=_AS_OF)
    report = _by_name(reports, "roll_mean_price_listing_5")
    assert report.status == DriftStatus.UNKNOWN
    assert report.score is None


# --- 5.6-T7 ---


def test_binary_flag_uses_js_not_psi() -> None:
    rng = np.random.default_rng(7)
    name = "competitor_price_change_flag"
    flags = (rng.random(600) < 0.3).astype(np.float64)
    history = _history(flags, flags.copy(), name=name)
    config = _drift_config()
    assert name in config.binary_drift_features
    reports = compute_feature_drift_report(history, config=config, as_of_tick=_AS_OF)
    report = _by_name(reports, name)
    assert report.metric_kind == DriftMetricKind.JENSEN_SHANNON
    assert report.ks_pvalue is None  # KS-путь только для continuous
    assert report.status != DriftStatus.BREACHED


# --- 5.6-T8 ---


def test_low_unique_feature_skipped() -> None:
    rng = np.random.default_rng(8)
    vals = rng.integers(0, 3, 600).astype(np.float64)  # 3 уникальных значения
    history = _history(vals, vals.copy(), name="ticks_since_own_price_change")
    config = _drift_config(fail_on_drift=True)
    reports = compute_feature_drift_report(history, config=config, as_of_tick=_AS_OF)
    report = _by_name(reports, "ticks_since_own_price_change")
    assert report.status == DriftStatus.SKIPPED
    assert report.metric_kind == DriftMetricKind.SKIPPED
