# Spec 015 §8 — paper-ready figures F1–F5 (PNG + PDF, B&W-distinguishable styles).
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import polars as pl

# Print-ready styles: unique (linestyle, marker) — not color-only (Spec 015 §8.1 / 15.5-T3).
F1_SERIES_STYLES: dict[float, dict[str, str]] = {
    0.0: {"linestyle": "solid", "marker": "o", "color": "0.1", "label": "0% ML"},
    0.5: {"linestyle": "dashed", "marker": "s", "color": "0.35", "label": "50% ML"},
    1.0: {"linestyle": "dotted", "marker": "^", "color": "0.55", "label": "100% ML"},
}

_F2_STYLE = {"linestyle": "solid", "marker": "D", "color": "0.2"}
_BAR_HATCHES = ("/", "\\\\", "x", "o", ".")


def _save_both(fig: plt.Figure, out_dir: Path, fig_id: str) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{fig_id}.png"
    pdf = out_dir / f"{fig_id}.pdf"
    fig.savefig(png, dpi=150, bbox_inches="tight")
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return {"png": png, "pdf": pdf}


def render_f1_price_path(tick_path: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    """F1: price vs tick by ml_share — prefers median+IQR band when present."""
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    shares = sorted(tick_path["ml_share"].unique().to_list())
    use_robust = "median" in tick_path.columns and "q25" in tick_path.columns
    for share in shares:
        style = F1_SERIES_STYLES.get(
            float(share),
            {
                "linestyle": "dashdot",
                "marker": "x",
                "color": "0.4",
                "label": f"{100 * share:.0f}% ML",
            },
        )
        sub = tick_path.filter(pl.col("ml_share") == share).sort("tick_id")
        x = sub["tick_id"].to_numpy()
        if use_robust:
            y = sub["median"].to_numpy()
            lo = sub["q25"].to_numpy()
            hi = sub["q75"].to_numpy()
        else:
            y = sub["mean"].to_numpy()
            lo = sub["lo"].to_numpy() if "lo" in sub.columns else y
            hi = sub["hi"].to_numpy() if "hi" in sub.columns else y
        ax.fill_between(x, lo, hi, color=style["color"], alpha=0.15)
        ax.plot(
            x,
            y,
            linestyle=style["linestyle"],
            marker=style["marker"],
            color=style["color"],
            label=style["label"],
            markersize=4,
            linewidth=1.5,
        )
    ax.set_xlabel("Tick")
    ax.set_ylabel("Median price" + (" (run median ± IQR)" if use_robust else ""))
    ax.set_title("F1: Price path by ML share")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.4)
    return _save_both(fig, out_dir, "F1")


def _summary_yerr(sub: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prefer robust median/IQR; fall back to mean/Student-t; clip non-finite."""
    if "median" in sub.columns and "q25" in sub.columns and "q75" in sub.columns:
        y = np.asarray(sub["median"].to_numpy(), dtype=np.float64)
        lo = np.asarray(sub["q25"].to_numpy(), dtype=np.float64)
        hi = np.asarray(sub["q75"].to_numpy(), dtype=np.float64)
    else:
        y = np.asarray(sub["mean"].to_numpy(), dtype=np.float64)
        lo = np.asarray(sub["lo"].to_numpy(), dtype=np.float64)
        hi = np.asarray(sub["hi"].to_numpy(), dtype=np.float64)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    lo = np.nan_to_num(lo, nan=y, posinf=y, neginf=y)
    hi = np.nan_to_num(hi, nan=y, posinf=y, neginf=y)
    # Guard exploding CI that breaks axes
    span = np.maximum(np.abs(y), 1.0)
    lo = np.maximum(lo, y - 50.0 * span)
    hi = np.minimum(hi, y + 50.0 * span)
    return y, lo, hi


def render_f2_volatility(summary: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    """F2: price_std vs ml_share with robust error bars when available."""
    sub = summary.filter(pl.col("metric") == "price_std").sort("ml_share")
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    x = sub["ml_share"].to_numpy()
    y, lo, hi = _summary_yerr(sub)
    yerr = np.vstack([np.maximum(y - lo, 0.0), np.maximum(hi - y, 0.0)])
    ax.errorbar(
        x,
        y,
        yerr=yerr,
        linestyle=_F2_STYLE["linestyle"],
        marker=_F2_STYLE["marker"],
        color=_F2_STYLE["color"],
        capsize=3,
        linewidth=1.5,
    )
    ax.set_xlabel("ML seller share")
    ax.set_ylabel("Price std")
    ax.set_title("F2: Volatility vs ML share")
    ax.grid(True, linestyle=":", alpha=0.4)
    return _save_both(fig, out_dir, "F2")


def render_f3_hhi(summary: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    """F3: HHI by ml_share (bars + robust CI)."""
    sub = summary.filter(pl.col("metric") == "hhi").sort("ml_share")
    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    x = np.arange(sub.height)
    y, lo, hi = _summary_yerr(sub)
    labels = [f"{100 * s:.0f}%" for s in sub["ml_share"].to_list()]
    bars = ax.bar(x, y, color="0.7", edgecolor="0.1")
    for i, bar in enumerate(bars):
        bar.set_hatch(_BAR_HATCHES[i % len(_BAR_HATCHES)])
    yerr = np.vstack([np.maximum(y - lo, 0.0), np.maximum(hi - y, 0.0)])
    ax.errorbar(x, y, yerr=yerr, fmt="none", ecolor="0.1", capsize=3)
    ax.set_xticks(x, labels)
    ax.set_xlabel("ML seller share")
    ax.set_ylabel("HHI (0–10000)")
    ax.set_title("F3: Market concentration (HHI)")
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    return _save_both(fig, out_dir, "F3")


def render_f4_welfare(summary: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    """F4: stacked CS / PS / platform by ml_share."""
    metrics = (
        ("consumer_surplus_proxy", "CS proxy", _BAR_HATCHES[0]),
        ("producer_surplus", "PS", _BAR_HATCHES[1]),
        ("platform_profit", "Platform", _BAR_HATCHES[2]),
    )
    shares = sorted(
        summary.filter(pl.col("metric") == "consumer_surplus_proxy")["ml_share"]
        .unique()
        .to_list()
    )
    fig, ax = plt.subplots(figsize=(6.0, 3.8))
    x = np.arange(len(shares))
    bottom = np.zeros(len(shares))
    for metric, label, hatch in metrics:
        vals = []
        for share in shares:
            row = summary.filter(
                (pl.col("metric") == metric) & (pl.col("ml_share") == share)
            )
            if row.height == 0:
                vals.append(0.0)
            elif "median" in row.columns:
                vals.append(float(row["median"][0]))
            else:
                vals.append(float(row["mean"][0]))
        arr = np.asarray(vals, dtype=np.float64)
        bars = ax.bar(x, arr, bottom=bottom, label=label, edgecolor="0.1", color="0.85")
        for bar in bars:
            bar.set_hatch(hatch)
        bottom = bottom + arr
    ax.set_xticks(x, [f"{100 * s:.0f}%" for s in shares])
    ax.set_xlabel("ML seller share")
    ax.set_ylabel("Welfare")
    ax.set_title("F4: Welfare comparison")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(True, axis="y", linestyle=":", alpha=0.4)
    return _save_both(fig, out_dir, "F4")


def render_f5_zipf(zipf: pl.DataFrame, out_dir: Path) -> dict[str, Path]:
    """F5: log(sales) vs log(rank) — Zipf / rank-size."""
    fig, ax = plt.subplots(figsize=(5.5, 3.8))
    shares = sorted(zipf["ml_share"].unique().to_list())
    fallback_styles = [
        {"linestyle": "solid", "marker": "o", "color": "0.15"},
        {"linestyle": "dashed", "marker": "s", "color": "0.45"},
    ]
    for i, share in enumerate(shares):
        style = F1_SERIES_STYLES.get(float(share), fallback_styles[i % len(fallback_styles)])
        sub = zipf.filter(pl.col("ml_share") == share).sort("rank")
        ax.plot(
            np.log(sub["rank"].to_numpy()),
            np.log(sub["sales"].to_numpy()),
            linestyle=style["linestyle"],
            marker=style["marker"],
            color=style.get("color", "0.3"),
            label=style.get("label", f"{100 * share:.0f}% ML"),
            markersize=4,
            linewidth=1.5,
        )
    ax.set_xlabel("log(rank)")
    ax.set_ylabel("log(sales)")
    ax.set_title("F5: Rank-size (Zipf)")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(True, linestyle=":", alpha=0.4)
    return _save_both(fig, out_dir, "F5")


def render_all_figures(
    out_dir: Path | str,
    *,
    summary: pl.DataFrame,
    tick_path: pl.DataFrame,
    zipf: pl.DataFrame,
) -> dict[str, dict[str, Path]]:
    """Render F1–F5 to PNG+PDF under out_dir."""
    root = Path(out_dir)
    return {
        "F1": render_f1_price_path(tick_path, root),
        "F2": render_f2_volatility(summary, root),
        "F3": render_f3_hhi(summary, root),
        "F4": render_f4_welfare(summary, root),
        "F5": render_f5_zipf(zipf, root),
    }
