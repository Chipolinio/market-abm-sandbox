# Назначение файла: детектор system_events и persist (Slice 8.3).
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import duckdb
import numpy as np
import polars as pl

from market_abm.analytics.store import AnalyticsStore
from market_abm.config.events import SystemEventsConfig
from market_abm.domain.constants import COL_SELLER_ID, COL_TICK_ID
from market_abm.domain.events import (
    COL_DISPLAY_CODE,
    COL_EVENT_ID,
    COL_EVENT_TYPE,
    COL_MESSAGE,
    COL_PAYLOAD_JSON,
    COL_SEVERITY,
    DISPLAY_CODE_BY_TYPE,
    SYSTEM_EVENTS_COLUMNS,
    SYSTEM_EVENTS_SCHEMA_DTYPES,
    SystemEventType,
)
from market_abm.domain.shocks import ShockType


def _events_schema() -> dict[str, pl.DataType]:
    return {name: getattr(pl, dtype) for name, dtype in SYSTEM_EVENTS_SCHEMA_DTYPES.items()}


def empty_system_events_df() -> pl.DataFrame:
    return pl.DataFrame(schema=_events_schema())


def _event_id(*, run_id: str, tick_id: int, event_type: SystemEventType, seq: int) -> str:
    return f"{run_id}:{tick_id}:{event_type.value}:{seq}"


def _pearson_corr(series_a: list[float], series_b: list[float]) -> float | None:
    if len(series_a) != len(series_b) or len(series_a) < 2:
        return None
    a = np.asarray(series_a, dtype=np.float64)
    b = np.asarray(series_b, dtype=np.float64)
    if np.std(a) == 0.0 or np.std(b) == 0.0:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def _seller_avg_price_series(
    prices_df: pl.DataFrame,
    *,
    seller_id: int,
    tick_min: int,
    tick_max: int,
) -> list[tuple[int, float]]:
    part = (
        prices_df.filter(
            (pl.col(COL_SELLER_ID) == seller_id)
            & (pl.col(COL_TICK_ID) >= tick_min)
            & (pl.col(COL_TICK_ID) <= tick_max)
        )
        .group_by(COL_TICK_ID)
        .agg(pl.col("price").mean().alias("avg_price"))
        .sort(COL_TICK_ID)
    )
    return [(int(r[COL_TICK_ID]), float(r["avg_price"])) for r in part.iter_rows(named=True)]


def _detect_collusion(
    store: AnalyticsStore,
    *,
    as_of_tick: int,
    config: SystemEventsConfig,
    run_id: str,
    seq_start: int,
) -> tuple[list[dict[str, object]], int]:
    cfg = config.collusion
    tick_min = max(0, as_of_tick - cfg.window_ticks + 1)
    prices_df = store.avg_price_by_listing_over_time()
    if prices_df.height == 0:
        return [], seq_start

    seller_ids = sorted(prices_df[COL_SELLER_ID].unique().to_list())
    events: list[dict[str, object]] = []
    seq = seq_start

    for seller_a, seller_b in combinations(seller_ids, 2):
        series_a = _seller_avg_price_series(
            prices_df, seller_id=int(seller_a), tick_min=tick_min, tick_max=as_of_tick
        )
        series_b = _seller_avg_price_series(
            prices_df, seller_id=int(seller_b), tick_min=tick_min, tick_max=as_of_tick
        )
        ticks_a = {t: v for t, v in series_a}
        ticks_b = {t: v for t, v in series_b}
        common_ticks = sorted(set(ticks_a) & set(ticks_b))
        if len(common_ticks) < cfg.min_observations:
            continue

        values_a = [ticks_a[t] for t in common_ticks]
        values_b = [ticks_b[t] for t in common_ticks]
        corr = _pearson_corr(values_a, values_b)
        if corr is None or corr <= cfg.min_correlation:
            continue

        event_type = SystemEventType.COLLUSION_DETECTED
        payload = {"seller_a": int(seller_a), "seller_b": int(seller_b), "correlation": corr}
        events.append(
            {
                COL_EVENT_ID: _event_id(
                    run_id=run_id, tick_id=as_of_tick, event_type=event_type, seq=seq
                ),
                COL_TICK_ID: as_of_tick,
                COL_EVENT_TYPE: event_type.value,
                COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
                COL_SEVERITY: "warning",
                COL_MESSAGE: f"Seller_{seller_a} and Seller_{seller_b} entered a dumping loop",
                COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
            }
        )
        seq += 1

    return events, seq


def _detect_flash_crash(
    store: AnalyticsStore,
    *,
    as_of_tick: int,
    config: SystemEventsConfig,
    run_id: str,
    seq_start: int,
) -> tuple[list[dict[str, object]], int]:
    cfg = config.flash_crash
    ref_tick = as_of_tick - cfg.window_ticks
    if ref_tick < 0:
        return [], seq_start

    index_df = store.price_index_by_tick()
    if index_df.height == 0:
        return [], seq_start

    current = index_df.filter(pl.col(COL_TICK_ID) == as_of_tick)
    reference = index_df.filter(pl.col(COL_TICK_ID) == ref_tick)
    if current.height == 0 or reference.height == 0:
        return [], seq_start

    current_median = float(current["median_price"][0])
    ref_median = float(reference["median_price"][0])
    if ref_median == 0.0:
        return [], seq_start

    drop = current_median / ref_median - 1.0
    if drop > -cfg.median_drop_pct:
        return [], seq_start

    pct = abs(drop) * 100.0
    event_type = SystemEventType.FLASH_CRASH
    payload = {"pct_drop": abs(drop), "window_ticks": cfg.window_ticks}
    event = {
        COL_EVENT_ID: _event_id(
            run_id=run_id, tick_id=as_of_tick, event_type=event_type, seq=seq_start
        ),
        COL_TICK_ID: as_of_tick,
        COL_EVENT_TYPE: event_type.value,
        COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
        COL_SEVERITY: "critical",
        COL_MESSAGE: (
            f"Market median price dropped {pct:.0f}% over {cfg.window_ticks} ticks"
        ),
        COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
    }
    return [event], seq_start + 1


def detect_system_events(
    store: AnalyticsStore,
    *,
    as_of_tick: int,
    config: SystemEventsConfig,
    run_id: str | None = None,
) -> pl.DataFrame:
    """Возвращает 0..N новых событий; не мутирует store."""
    if as_of_tick % config.check_every_n_ticks != 0:
        return empty_system_events_df()

    resolved_run_id = run_id or store._run_id_from_manifest()
    events: list[dict[str, object]] = []
    seq = 0

    collusion_events, seq = _detect_collusion(
        store, as_of_tick=as_of_tick, config=config, run_id=resolved_run_id, seq_start=seq
    )
    events.extend(collusion_events)

    flash_events, _seq = _detect_flash_crash(
        store, as_of_tick=as_of_tick, config=config, run_id=resolved_run_id, seq_start=seq
    )
    events.extend(flash_events)

    if not events:
        return empty_system_events_df()
    return pl.DataFrame(events).select(list(SYSTEM_EVENTS_COLUMNS))


def build_demand_shock_event(
    *,
    run_id: str,
    tick_id: int,
    seq: int,
    pct_drop: float,
    shock_type: ShockType = ShockType.DEMAND_CRASH,
) -> dict[str, object]:
    event_type = SystemEventType.DEMAND_SHOCK
    if shock_type == ShockType.DEMAND_BOOM:
        message = f"Buyer budgets increased by {pct_drop:.0f}%"
    else:
        message = f"Buyer budgets cut by {pct_drop:.0f}%"
    payload = {"pct_drop": pct_drop, "shock_type": shock_type.value}
    return {
        COL_EVENT_ID: _event_id(run_id=run_id, tick_id=tick_id, event_type=event_type, seq=seq),
        COL_TICK_ID: tick_id,
        COL_EVENT_TYPE: event_type.value,
        COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
        COL_SEVERITY: "info",
        COL_MESSAGE: message,
        COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
    }


def build_tick_pulse_event(
    *,
    run_id: str,
    tick_id: int,
    seq: int,
    gmv: float,
    transaction_count: int,
    active_sellers: int,
    bankrupt_sellers: int,
) -> dict[str, object]:
    """Один info-пульс на тик — непрерывный cyber-log даже без аномалий."""
    event_type = SystemEventType.TICK_PULSE
    payload = {
        "gmv": gmv,
        "transaction_count": transaction_count,
        "active_sellers": active_sellers,
        "bankrupt_sellers": bankrupt_sellers,
    }
    return {
        COL_EVENT_ID: _event_id(run_id=run_id, tick_id=tick_id, event_type=event_type, seq=seq),
        COL_TICK_ID: tick_id,
        COL_EVENT_TYPE: event_type.value,
        COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
        COL_SEVERITY: "info",
        COL_MESSAGE: (
            f"GMV {gmv:.0f}, {transaction_count} tx, "
            f"{active_sellers} active / {bankrupt_sellers} bankrupt sellers"
        ),
        COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
    }


def build_bankruptcy_event(
    *,
    run_id: str,
    tick_id: int,
    seller_id: int,
    seq: int,
) -> dict[str, object]:
    event_type = SystemEventType.BANKRUPTCY
    payload = {"seller_id": seller_id}
    return {
        COL_EVENT_ID: _event_id(run_id=run_id, tick_id=tick_id, event_type=event_type, seq=seq),
        COL_TICK_ID: tick_id,
        COL_EVENT_TYPE: event_type.value,
        COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
        COL_SEVERITY: "warning",
        COL_MESSAGE: f"Seller_{seller_id} depleted working capital and exited the market",
        COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
    }


def build_mass_bankruptcy_event(
    *,
    run_id: str,
    tick_id: int,
    seller_ids: list[int],
    seq: int,
) -> dict[str, object]:
    """Агрегированное событие массового банкротства (>3 рядовых селлеров за тик)."""
    event_type = SystemEventType.BANKRUPTCY
    count = len(seller_ids)
    preview = ", ".join(str(sid) for sid in seller_ids[:8])
    suffix = "..." if count > 8 else ""
    payload = {"seller_ids": seller_ids, "count": count, "aggregated": True}
    return {
        COL_EVENT_ID: _event_id(
            run_id=run_id,
            tick_id=tick_id,
            event_type=event_type,
            seq=seq,
        ),
        COL_TICK_ID: tick_id,
        COL_EVENT_TYPE: event_type.value,
        COL_DISPLAY_CODE: DISPLAY_CODE_BY_TYPE[event_type],
        COL_SEVERITY: "warning",
        COL_MESSAGE: (
            f"Из симуляции массово выбыло {count} селлеров (ID: {preview}{suffix})"
        ),
        COL_PAYLOAD_JSON: json.dumps(payload, separators=(",", ":")),
    }


def coalesce_bankruptcy_events(
    *,
    run_id: str,
    tick_id: int,
    bankrupt_seller_ids: list[int],
    top_seller_ids: frozenset[int],
    seq_start: int,
) -> tuple[list[dict[str, object]], int]:
    """
    Топ-3 игрока — штучные события; >3 рядовых банкротств — одна групповая сводка.
    """
    if not bankrupt_seller_ids:
        return [], seq_start

    events: list[dict[str, object]] = []
    seq = seq_start
    vip = [sid for sid in bankrupt_seller_ids if sid in top_seller_ids]
    routine = [sid for sid in bankrupt_seller_ids if sid not in top_seller_ids]

    for seller_id in vip:
        events.append(
            build_bankruptcy_event(
                run_id=run_id,
                tick_id=tick_id,
                seller_id=seller_id,
                seq=seq,
            )
        )
        seq += 1

    if len(routine) > 3:
        events.append(
            build_mass_bankruptcy_event(
                run_id=run_id,
                tick_id=tick_id,
                seller_ids=routine,
                seq=seq,
            )
        )
        seq += 1
    else:
        for seller_id in routine:
            events.append(
                build_bankruptcy_event(
                    run_id=run_id,
                    tick_id=tick_id,
                    seller_id=seller_id,
                    seq=seq,
                )
            )
            seq += 1

    return events, seq


def _system_events_fragment_path(events_dir: Path, tick_id: int) -> Path:
    """Уникальный fragment-файл на append — без перезаписи общего events.parquet."""
    prefix = f"evt_{tick_id:06d}_"
    seq = sum(1 for _ in events_dir.glob(f"{prefix}*.parquet"))
    return events_dir / f"{prefix}{seq:04d}.parquet"


def append_system_events(
    run_root: Path,
    events_df: pl.DataFrame,
    con: duckdb.DuckDBPyConnection,
) -> None:
    """Append-only: каждый batch пишется в отдельный evt_{tick}_{seq}.parquet."""
    if events_df.height == 0:
        return
    if list(events_df.columns) != list(SYSTEM_EVENTS_COLUMNS):
        raise ValueError(
            f"events_df columns mismatch: expected {list(SYSTEM_EVENTS_COLUMNS)}, "
            f"got {events_df.columns}"
        )

    run_root = Path(run_root)
    events_dir = run_root / "system_events"
    events_dir.mkdir(parents=True, exist_ok=True)
    tick_id = int(events_df[COL_TICK_ID].max())
    fragment_path = _system_events_fragment_path(events_dir, tick_id)

    arrow_table = events_df.to_arrow()
    con.register("_new_events", arrow_table)
    try:
        con.execute(
            "COPY (SELECT * FROM _new_events) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(fragment_path)],
        )
    finally:
        con.unregister("_new_events")
