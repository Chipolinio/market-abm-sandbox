/**
 * Dense top-N listing series transforms (Spec 007 §4.4, Slice 7.7).
 */
import {
  capSeries,
  downsampleForRender,
  renderCapForTier,
  upsertMergeByTickId,
} from "./chartSeries";
import type {
  ListingMetricKey,
  ListingMetricPoint,
  ListingMetricSeries,
  ListingSeriesData,
  ListingWideRow,
} from "./types";

export const DEFAULT_TOP_LISTINGS_LIMIT = 10;
export const MAX_DENSE_LISTING_SERIES = 10;

export function listingSeriesKey(listingId: number, metric: ListingMetricKey): string {
  return `listing_${listingId}_${metric}`;
}

export function listingLineKey(listingId: number): string {
  return `listing_${listingId}`;
}

function metricValue(point: ListingMetricPoint, metric: ListingMetricKey): number | null {
  if (metric === "price") {
    return point.price;
  }
  if (metric === "gmv") {
    return point.gmv;
  }
  return point.volume;
}

/** Pivot long listing series into wide Recharts rows (≤10 series). */
export function pivotListingMetricsToWide(
  listings: ListingSeriesData[],
  metric: ListingMetricKey,
): ListingWideRow[] {
  const capped = listings.slice(0, MAX_DENSE_LISTING_SERIES);
  const tickIds = new Set<number>();
  for (const listing of capped) {
    for (const point of listing.points) {
      tickIds.add(point.tick_id);
    }
  }

  return [...tickIds]
    .sort((a, b) => a - b)
    .map((tick_id) => {
      const row: ListingWideRow = { tick_id };
      for (const listing of capped) {
        const point = listing.points.find((p) => p.tick_id === tick_id);
        const key = listingLineKey(listing.listing_id);
        row[key] = point === undefined ? null : metricValue(point, metric);
      }
      return row;
    });
}

export function upsertListingPoint(
  series: ListingMetricSeries,
  point: ListingMetricPoint,
): ListingMetricSeries {
  const asTick = { ...point };
  const merged = upsertMergeByTickId(
    series as Map<number, ListingMetricPoint>,
    [asTick],
  ) as ListingMetricSeries;
  return capSeries(merged, "dense") as ListingMetricSeries;
}

export function mergeListingBackfill(
  existing: ListingMetricSeries,
  incoming: ListingMetricPoint[],
  options?: { rejectBelowMax?: boolean },
): ListingMetricSeries {
  const merged = upsertMergeByTickId(existing, incoming, options) as ListingMetricSeries;
  return capSeries(merged, "dense") as ListingMetricSeries;
}

export function downsampleListingWide(rows: ListingWideRow[]): ListingWideRow[] {
  return downsampleForRender(rows, renderCapForTier("dense"));
}

export function hasPlottableListingWide(
  rows: ListingWideRow[],
  seriesKeys: string[],
): boolean {
  return rows.some((row) =>
    seriesKeys.some((key) => {
      const value = row[key];
      return value !== null && value !== undefined && value !== 0;
    }),
  );
}
