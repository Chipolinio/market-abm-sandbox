import { describe, expect, it } from "vitest";

import {
  DENSE_RENDER_MAX,
  DENSE_SERIES_CAP,
  MACRO_RENDER_MAX,
  MACRO_SERIES_CAP,
  downsampleForRender,
  renderCapForTier,
  seriesToSortedArray,
  toPriceChartData,
  upsertMergeByTickId,
  upsertTickPoint,
} from "../state/chartSeries";
import type { PriceTickPoint, TickPoint } from "../state/types";

function pricePoint(tick_id: number, ts?: string): PriceTickPoint {
  return {
    tick_id,
    p10: tick_id,
    p50: tick_id + 0.5,
    p90: tick_id + 1,
    mean_price: tick_id + 0.5,
    timestamp_utc: ts ?? `2026-06-05T00:00:${String(tick_id).padStart(2, "0")}Z`,
  };
}

function rangePoints(from: number, to: number): PriceTickPoint[] {
  const out: PriceTickPoint[] = [];
  for (let tick_id = from; tick_id <= to; tick_id += 1) {
    out.push(pricePoint(tick_id));
  }
  return out;
}

describe("upsertTickPoint", () => {
  it("dedupes_by_tick_id", () => {
    const empty = new Map<number, TickPoint>();
    const first = upsertTickPoint(empty, pricePoint(5, "2026-06-05T00:00:05Z"), "macro");
    const updated: PriceTickPoint = {
      ...pricePoint(5, "2026-06-05T00:00:06Z"),
      mean_price: 99,
    };
    const second = upsertTickPoint(first, updated, "macro");

    expect(second.size).toBe(1);
    expect((second.get(5) as PriceTickPoint).mean_price).toBe(99);
  });
});

describe("capSeries", () => {
  it("capMacroSeries_drops_oldest_beyond_3600", () => {
    let series = new Map<number, TickPoint>();
    for (let i = 0; i <= MACRO_SERIES_CAP; i += 1) {
      series = upsertTickPoint(series, pricePoint(i), "macro");
    }
    expect(series.size).toBe(MACRO_SERIES_CAP);
    expect(series.has(0)).toBe(false);
    expect(series.has(MACRO_SERIES_CAP)).toBe(true);
  });

  it("capDenseSeries_drops_oldest_beyond_600", () => {
    let series = new Map<number, TickPoint>();
    for (let i = 0; i <= DENSE_SERIES_CAP; i += 1) {
      series = upsertTickPoint(series, pricePoint(i), "dense");
    }
    expect(series.size).toBe(DENSE_SERIES_CAP);
    expect(series.has(0)).toBe(false);
    expect(series.has(DENSE_SERIES_CAP)).toBe(true);
  });
});

describe("toPriceChartData", () => {
  it("maps_quantiles", () => {
    const rows = toPriceChartData([pricePoint(3)]);
    expect(rows).toEqual([
      {
        tick_id: 3,
        p10: 3,
        p50: 3.5,
        p90: 4,
        mean_price: 3.5,
      },
    ]);
  });
});

describe("upsertMergeByTickId", () => {
  it("backfill_race_preserves_ws_ticks", () => {
    const live = new Map<number, TickPoint>([
      [101, pricePoint(101, "2026-06-05T00:01:41Z")],
      [102, pricePoint(102, "2026-06-05T00:01:42Z")],
    ]);
    const merged = upsertMergeByTickId(live, rangePoints(0, 100));
    const ids = [...merged.keys()].sort((a, b) => a - b);

    expect(ids).toHaveLength(103);
    expect(ids[0]).toBe(0);
    expect(ids[ids.length - 1]).toBe(102);
    expect((merged.get(101) as PriceTickPoint).timestamp_utc).toBe("2026-06-05T00:01:41Z");
    expect((merged.get(102) as PriceTickPoint).timestamp_utc).toBe("2026-06-05T00:01:42Z");
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("filters_stale_backfill", () => {
    const live = new Map<number, TickPoint>([
      [101, pricePoint(101)],
      [102, pricePoint(102)],
    ]);
    const merged = upsertMergeByTickId(live, rangePoints(0, 100), {
      rejectBelowMax: true,
    });

    expect(merged.size).toBe(2);
    expect(merged.has(100)).toBe(false);
    expect(merged.has(101)).toBe(true);
    expect(merged.has(102)).toBe(true);
  });
});

describe("downsampleForRender", () => {
  it("limits_svg_points", () => {
    const data = rangePoints(0, 2999);
    const macro = downsampleForRender(data, MACRO_RENDER_MAX);
    const dense = downsampleForRender(data, DENSE_RENDER_MAX);

    expect(macro.length).toBeLessThanOrEqual(MACRO_RENDER_MAX);
    expect(dense.length).toBeLessThanOrEqual(DENSE_RENDER_MAX);
    expect(macro[0]!.tick_id).toBe(0);
    expect(macro[macro.length - 1]!.tick_id).toBe(2999);
    expect(dense[0]!.tick_id).toBe(0);
    expect(dense[dense.length - 1]!.tick_id).toBe(2999);
  });

  it("renderCapForTier matches spec", () => {
    expect(renderCapForTier("macro")).toBe(MACRO_RENDER_MAX);
    expect(renderCapForTier("dense")).toBe(DENSE_RENDER_MAX);
  });
});

describe("seriesToSortedArray", () => {
  it("sorts by tick_id ascending", () => {
    const map = upsertMergeByTickId(new Map(), [pricePoint(2), pricePoint(0), pricePoint(1)]);
    const arr = seriesToSortedArray(map);
    expect(arr.map((p) => p.tick_id)).toEqual([0, 1, 2]);
  });
});
