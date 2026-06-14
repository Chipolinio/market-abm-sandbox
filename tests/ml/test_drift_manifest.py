# Назначение файла: RED-тесты слайса 5.6b — проводка drift в manifest (Spec 005 §10.4, опционально).
# Базовая идея: compute_feature_drift_report → drift_reports_to_alerts → append_drift_alerts (write) →
# AnalyticsStore.drift_alerts (query); гейтинг по should_check_drift (каждые N тиков). Без переписи runner.
from __future__ import annotations

from pathlib import Path

import numpy as np
import polars as pl

from market_abm.analytics.persist import append_drift_alerts, init_run_directory
from market_abm.analytics.store import AnalyticsStore
from market_abm.config.ml_repricing import DriftMonitorConfig
from market_abm.config.runner import PersistenceConfig, SimulationRunConfig
from market_abm.domain.constants import COL_BUYER_ID, COL_LISTING_ID, COL_SELLER_ID, COL_TICK_ID
from tests.helpers.reference_snapshots import stub_buyers_df, stub_sellers_df
from market_abm.ml.drift import (
    compute_feature_drift_report,
    drift_reports_to_alerts,
    should_check_drift,
)

_REF_TICK = 10
_CUR_TICK = 30
_AS_OF = 40


def _run_root(tmp_path: Path, *, run_id: str = "drift-manifest") -> Path:
    config = SimulationRunConfig(
        seed=1,
        persistence=PersistenceConfig(enabled=True, base_dir=str(tmp_path), run_id=run_id),
    )
    buyers = stub_buyers_df([0])
    sellers = stub_sellers_df([0])
    listings = pl.DataFrame({COL_LISTING_ID: [0], COL_SELLER_ID: [0]}).with_columns(
        pl.col(COL_LISTING_ID).cast(pl.Int32),
        pl.col(COL_SELLER_ID).cast(pl.Int32),
    )
    ctx = init_run_directory(
        config,
        run_id=run_id,
        buyers_df=buyers,
        sellers_df=sellers,
        listings_df=listings,
        n_ticks=5,
    )
    return ctx.run_root


def _history(ref_vals: np.ndarray, cur_vals: np.ndarray, *, name: str) -> pl.DataFrame:
    ref = pl.DataFrame(
        {COL_TICK_ID: [_REF_TICK] * ref_vals.shape[0], name: ref_vals.astype(np.float64)}
    )
    cur = pl.DataFrame(
        {COL_TICK_ID: [_CUR_TICK] * cur_vals.shape[0], name: cur_vals.astype(np.float64)}
    )
    return pl.concat([ref, cur]).with_columns(pl.col(COL_TICK_ID).cast(pl.Int32))


def _drift_config(**overrides: object) -> DriftMonitorConfig:
    base: dict[str, object] = dict(
        reference_window_ticks=20,
        current_window_ticks=20,
        min_samples_for_drift=500,
    )
    base.update(overrides)
    return DriftMonitorConfig(**base)


def _query_alerts(run_root: Path) -> list[dict[str, object]]:
    store = AnalyticsStore(run_root)
    try:
        return store.drift_alerts()
    finally:
        store.close()


# --- 5.6b-T1 ---


def test_append_and_query_drift_alerts(tmp_path: Path) -> None:
    run_root = _run_root(tmp_path)
    alert = {
        "as_of_tick": 40,
        "feature_name": "competitor_price_gap",
        "status": "breached",
        "metric_kind": "psi",
        "score": 0.5,
        "ks_pvalue": 0.01,
        "n_reference": 600,
        "n_current": 600,
        "n_unique_reference": 300,
    }
    append_drift_alerts(run_root, [alert])

    got = _query_alerts(run_root)
    assert len(got) == 1
    assert got[0]["status"] == "breached"
    assert got[0]["feature_name"] == "competitor_price_gap"


# --- 5.6b-T2 ---


def test_drift_alerts_accumulate_over_checks(tmp_path: Path) -> None:
    run_root = _run_root(tmp_path)
    for tick in (10, 20, 30):
        append_drift_alerts(
            run_root,
            [
                {
                    "as_of_tick": tick,
                    "feature_name": "x",
                    "status": "ok",
                    "metric_kind": "psi",
                    "score": 0.0,
                    "ks_pvalue": 1.0,
                    "n_reference": 600,
                    "n_current": 600,
                    "n_unique_reference": 300,
                }
            ],
        )
    got = _query_alerts(run_root)
    assert [a["as_of_tick"] for a in got] == [10, 20, 30]


# --- 5.6b-T3 (compose: compute → serialize → append → query) ---


def test_compute_serialize_persist_query_breach(tmp_path: Path) -> None:
    run_root = _run_root(tmp_path)
    rng = np.random.default_rng(3)
    ref = rng.normal(0.0, 1.0, 600)
    cur = rng.normal(3.0, 1.0, 600)
    history = _history(ref, cur, name="competitor_price_gap")

    reports = compute_feature_drift_report(
        history, config=_drift_config(), as_of_tick=_AS_OF
    )
    alerts = drift_reports_to_alerts(reports)
    append_drift_alerts(run_root, alerts)

    got = _query_alerts(run_root)
    breached = [a for a in got if a["status"] == "breached"]
    assert any(a["feature_name"] == "competitor_price_gap" for a in breached)
    assert breached[0]["metric_kind"] == "psi"
    assert breached[0]["score"] is not None


# --- 5.6b-T4 (гейтинг по should_check_drift) ---


def test_drift_monitor_respects_check_interval(tmp_path: Path) -> None:
    run_root = _run_root(tmp_path)
    config = _drift_config(check_every_n_ticks=10)
    fired: list[int] = []
    for tick in range(26):
        if not should_check_drift(tick, config):
            continue
        fired.append(tick)
        append_drift_alerts(
            run_root,
            [
                {
                    "as_of_tick": tick,
                    "feature_name": "x",
                    "status": "skipped",
                    "metric_kind": "skipped",
                    "score": None,
                    "ks_pvalue": None,
                    "n_reference": 0,
                    "n_current": 0,
                    "n_unique_reference": 0,
                }
            ],
        )
    got = _query_alerts(run_root)
    assert fired == [0, 10, 20]
    assert sorted({a["as_of_tick"] for a in got}) == [0, 10, 20]
