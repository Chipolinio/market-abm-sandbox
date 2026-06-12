import { apiFetch } from "./client";
import type { DemandMatrixResponse } from "@/types/demandMatrix";
import type { SystemEventsResponse } from "@/types/events";
import type { MarketLeadersResponse } from "@/types/leaders";
import type { GmvPoint, ListingSeries, PriceIndexPoint } from "./types";
import { DEFAULT_TOP_LISTINGS_LIMIT } from "@/state/listingSeries";

type PriceIndexResponse = {
  run_id: string;
  points: PriceIndexPoint[];
};

type GmvByTickResponse = {
  run_id: string;
  points: GmvPoint[];
};

export function fetchPriceIndex(): Promise<PriceIndexResponse> {
  return apiFetch<PriceIndexResponse>("/api/v1/analytics/price-index");
}

export function fetchGmvByTick(): Promise<GmvByTickResponse> {
  return apiFetch<GmvByTickResponse>("/api/v1/analytics/gmv-by-tick");
}

type TopListingsResponse = {
  run_id: string;
  listings: ListingSeries[];
};

export function fetchTopListings(
  limit: number = DEFAULT_TOP_LISTINGS_LIMIT,
): Promise<TopListingsResponse> {
  return apiFetch<TopListingsResponse>(`/api/v1/analytics/top-listings?limit=${limit}`);
}

/** Full seller registry (matches max n_sellers in session configure). */
export const SELLERS_REGISTRY_LIMIT = 1000;

/** Top-N ribbon in Zone D. */
export const TOP_SELLERS_RIBBON_LIMIT = 3;

export function fetchMarketLeaders(
  tickId: number,
  limit: number = 5,
): Promise<MarketLeadersResponse> {
  return apiFetch<MarketLeadersResponse>(
    `/api/v1/analytics/market-leaders?tick_id=${tickId}&limit=${limit}`,
  );
}

export function fetchDemandMatrix(tickId: number): Promise<DemandMatrixResponse> {
  return apiFetch<DemandMatrixResponse>(`/api/v1/analytics/demand-matrix?tick_id=${tickId}`);
}

export function fetchSystemEvents(
  limit: number = 200,
  sinceTick?: number,
): Promise<SystemEventsResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sinceTick !== undefined) {
    params.set("since_tick", String(sinceTick));
  }
  return apiFetch<SystemEventsResponse>(`/api/v1/analytics/system-events?${params.toString()}`);
}
