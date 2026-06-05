import { describe, expect, it } from "vitest";

import {
  DEFAULT_TOP_LISTINGS_LIMIT,
  listingSeriesKey,
  mergeListingBackfill,
  pivotListingMetricsToWide,
  upsertListingPoint,
} from "../state/listingSeries";
import type { ListingSeriesData } from "../state/types";

const sampleListings: ListingSeriesData[] = [
  {
    listing_id: 0,
    seller_id: 10,
    points: [
      { tick_id: 0, price: 100, gmv: 50, volume: 1 },
      { tick_id: 1, price: 110, gmv: 0, volume: 0 },
    ],
  },
  {
    listing_id: 2,
    seller_id: 20,
    points: [{ tick_id: 0, price: 200, gmv: 80, volume: 2 }],
  },
];

describe("listingSeries", () => {
  it("pivotListingMetricsToWide_builds_price_gmv_volume_columns", () => {
    const priceWide = pivotListingMetricsToWide(sampleListings, "price");
    expect(priceWide).toHaveLength(2);
    expect(priceWide[0]).toMatchObject({ tick_id: 0, listing_0: 100, listing_2: 200 });
    expect(priceWide[1]).toMatchObject({ tick_id: 1, listing_0: 110 });

    const gmvWide = pivotListingMetricsToWide(sampleListings, "gmv");
    expect(gmvWide[0]).toMatchObject({ tick_id: 0, listing_0: 50, listing_2: 80 });

    const volWide = pivotListingMetricsToWide(sampleListings, "volume");
    expect(volWide[0]).toMatchObject({ tick_id: 0, listing_0: 1, listing_2: 2 });
  });

  it("upsertListingPoint_caps_dense_tier", () => {
    let map = new Map<number, { tick_id: number; price: number | null; gmv: number; volume: number }>();
    for (let i = 0; i <= 600; i += 1) {
      map = upsertListingPoint(map, {
        tick_id: i,
        price: i,
        gmv: 0,
        volume: 0,
      });
    }
    expect(map.size).toBe(600);
    expect(map.has(0)).toBe(false);
    expect(map.has(600)).toBe(true);
    expect(listingSeriesKey(0, "price")).toBe("listing_0_price");
  });

  it("mergeListingBackfill_rejects_stale_ticks", () => {
    const live = new Map<number, { tick_id: number; price: number | null; gmv: number; volume: number }>([
      [5, { tick_id: 5, price: 5, gmv: 1, volume: 1 }],
    ]);
    const merged = mergeListingBackfill(live, sampleListings[0]!.points, { rejectBelowMax: true });
    expect(merged.size).toBe(1);
    expect(merged.has(0)).toBe(false);
    expect(merged.has(5)).toBe(true);
  });

  it("default_top_listings_limit_is_10", () => {
    expect(DEFAULT_TOP_LISTINGS_LIMIT).toBe(10);
  });
});
