# Spec 015 slice 15.5 — paper figures F1–F5 + docs/paper presence.
from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from experiments.figures import F1_SERIES_STYLES, render_all_figures


def _synthetic_summary() -> pl.DataFrame:
    rows: list[dict] = []
    for share in (0.0, 0.5, 1.0):
        for metric, mean in [
            ("median_price", 10.0 + 5 * share),
            ("price_std", 1.0 + share),
            ("hhi", 1000.0 + 500 * share),
            ("consumer_surplus_proxy", 100.0 - 10 * share),
            ("producer_surplus", 50.0 + 20 * share),
            ("platform_profit", 15.0 + 5 * share),
            ("gmv", 200.0),
            ("n_tx", 10.0),
        ]:
            rows.append(
                {
                    "metric": metric,
                    "ml_share": share,
                    "window": "post_burn_in",
                    "mean": mean,
                    "lo": mean * 0.9,
                    "hi": mean * 1.1,
                    "std": 0.5,
                    "n_runs": 3,
                }
            )
    return pl.DataFrame(rows)


def _synthetic_tick_path() -> pl.DataFrame:
    rows: list[dict] = []
    for share in (0.0, 0.5, 1.0):
        for tick in range(0, 30):
            mean = 10.0 + share * 2.0 + (0.05 * tick if tick >= 15 else 0.0)
            rows.append(
                {
                    "tick_id": tick,
                    "ml_share": share,
                    "metric": "median_price",
                    "mean": mean,
                    "lo": mean - 0.5,
                    "hi": mean + 0.5,
                }
            )
    return pl.DataFrame(rows)


def _synthetic_zipf() -> pl.DataFrame:
    rows: list[dict] = []
    for share in (0.0, 1.0):
        for rank in range(1, 11):
            rows.append(
                {
                    "ml_share": share,
                    "rank": rank,
                    "sales": 1000.0 / (rank**1.2),
                }
            )
    return pl.DataFrame(rows)


def test_15_5_t1_figure_scripts_smoke(tmp_path: Path) -> None:
    """15.5-T1: synthetic aggregate → F1–F5 exist as PNG and PDF."""
    out = tmp_path / "figures"
    paths = render_all_figures(
        out,
        summary=_synthetic_summary(),
        tick_path=_synthetic_tick_path(),
        zipf=_synthetic_zipf(),
    )
    for fig_id in ("F1", "F2", "F3", "F4", "F5"):
        assert (out / f"{fig_id}.png").is_file(), fig_id
        assert (out / f"{fig_id}.pdf").is_file(), fig_id
        assert fig_id in paths


def test_15_5_t2_paper_docs_exist() -> None:
    """15.5-T2: five markdown files in docs/paper/ are non-empty."""
    root = Path(__file__).resolve().parents[2] / "docs" / "paper"
    required = [
        "research-questions.md",
        "odd-protocol.md",
        "parameter-calibration.md",
        "related-work.md",
        "limitations.md",
    ]
    for name in required:
        path = root / name
        assert path.is_file(), name
        assert path.read_text(encoding="utf-8").strip(), name


def test_15_5_t3_figures_bw_distinguishable_styles() -> None:
    """15.5-T3: F1 series use distinct linestyle and/or marker (not color-only)."""
    assert len(F1_SERIES_STYLES) >= 2
    styles = list(F1_SERIES_STYLES.values())
    pairs = {(s["linestyle"], s["marker"]) for s in styles}
    assert len(pairs) == len(styles), "each F1 series must have unique (linestyle, marker)"
