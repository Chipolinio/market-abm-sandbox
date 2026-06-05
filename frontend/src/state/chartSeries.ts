/**
 * Pure transforms for chart ring-buffers (Spec 007 §4.4–4.5).
 * Map<tick_id, Point> — single source of truth; no React imports.
 */
import type {
  GmvTickPoint,
  PriceChartRow,
  PriceTickPoint,
  SeriesTier,
  TickPoint,
  TickSeries,
} from "./types";

export const MACRO_SERIES_CAP = 3600;
export const DENSE_SERIES_CAP = 600;
export const MACRO_RENDER_MAX = 1200;
export const DENSE_RENDER_MAX = 600;

export type UpsertMergeOptions = {
  /** Skip backfill points with tick_id <= max(existing) — anti-race (§4.5). */
  rejectBelowMax?: boolean;
};

function capForTier(tier: SeriesTier): number {
  return tier === "macro" ? MACRO_SERIES_CAP : DENSE_SERIES_CAP;
}

function maxTickId(series: TickSeries): number {
  if (series.size === 0) {
    return -1;
  }
  return Math.max(...series.keys());
}

function isNewerPoint(current: TickPoint | undefined, incoming: TickPoint): boolean {
  if (current === undefined) {
    return true;
  }
  if (current.timestamp_utc === undefined || incoming.timestamp_utc === undefined) {
    return true;
  }
  return incoming.timestamp_utc >= current.timestamp_utc;
}

/** FIFO cap: drop lowest tick_id values when over limit. */
export function capSeries(series: TickSeries, tier: SeriesTier): TickSeries {
  const limit = capForTier(tier);
  if (series.size <= limit) {
    return series;
  }
  const sortedIds = [...series.keys()].sort((a, b) => a - b);
  const dropCount = series.size - limit;
  const next = new Map(series);
  for (let i = 0; i < dropCount; i += 1) {
    next.delete(sortedIds[i]!);
  }
  return next;
}

export function upsertTickPoint(
  series: TickSeries,
  point: TickPoint,
  tier: SeriesTier,
): TickSeries {
  const next = new Map(series);
  const existing = next.get(point.tick_id);
  if (isNewerPoint(existing, point)) {
    next.set(point.tick_id, point);
  }
  return capSeries(next, tier);
}

/**
 * Merge REST backfill or WS batch into existing series (upsert by tick_id).
 * Never clears the map — only adds/replaces keys.
 */
export function upsertMergeByTickId(
  existing: TickSeries,
  incoming: TickPoint[],
  options?: UpsertMergeOptions,
): TickSeries {
  const rejectBelowMax = options?.rejectBelowMax ?? false;
  const maxLive = maxTickId(existing);

  let batch = incoming;
  if (rejectBelowMax && maxLive >= 0) {
    batch = incoming.filter((p) => p.tick_id > maxLive);
  }

  const next = new Map(existing);
  for (const point of batch) {
    const current = next.get(point.tick_id);
    if (isNewerPoint(current, point)) {
      next.set(point.tick_id, point);
    }
  }
  return next;
}

export function seriesToSortedArray(series: TickSeries): TickPoint[] {
  return [...series.values()].sort((a, b) => a.tick_id - b.tick_id);
}

export function toPriceChartData(points: PriceTickPoint[]): PriceChartRow[] {
  return points.map((p) => ({
    tick_id: p.tick_id,
    p10: p.p10,
    p50: p.p50,
    p90: p.p90,
    mean_price: p.mean_price,
  }));
}

/**
 * Uniform stride downsampling before Recharts render (§4.4).
 * Always keeps first and last point when len > maxRenderPoints.
 */
export function downsampleForRender<T extends { tick_id: number }>(
  data: T[],
  maxRenderPoints: number,
): T[] {
  if (data.length <= maxRenderPoints || maxRenderPoints < 2) {
    return data;
  }

  const sorted = [...data].sort((a, b) => a.tick_id - b.tick_id);
  const stride = (sorted.length - 1) / (maxRenderPoints - 1);
  const result: T[] = [];
  const used = new Set<number>();

  for (let i = 0; i < maxRenderPoints; i += 1) {
    const idx = i === maxRenderPoints - 1 ? sorted.length - 1 : Math.round(i * stride);
    if (!used.has(idx)) {
      used.add(idx);
      result.push(sorted[idx]!);
    }
  }

  if (result[result.length - 1]?.tick_id !== sorted[sorted.length - 1]!.tick_id) {
    result.push(sorted[sorted.length - 1]!);
  }

  return result.sort((a, b) => a.tick_id - b.tick_id);
}

export function renderCapForTier(tier: SeriesTier): number {
  return tier === "macro" ? MACRO_RENDER_MAX : DENSE_RENDER_MAX;
}

/** True when at least one point has a non-null, non-zero price signal. */
export function hasPlottablePriceData(rows: PriceChartRow[]): boolean {
  return rows.some(
    (r) =>
      (r.p50 !== null && r.p50 !== 0) ||
      (r.p10 !== null && r.p10 !== 0) ||
      (r.p90 !== null && r.p90 !== 0) ||
      (r.mean_price !== null && r.mean_price !== 0),
  );
}

/** True when at least one point has GMV or transaction activity. */
export function hasPlottableGmvData(points: GmvTickPoint[]): boolean {
  return points.some((p) => p.gmv > 0 || (p.transaction_count ?? 0) > 0);
}
