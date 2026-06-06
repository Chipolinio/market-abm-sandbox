import { apiFetch } from "./client";
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

export function fetchMarketLeaders(limit: number = 5): Promise<MarketLeadersResponse> {
  return apiFetch<MarketLeadersResponse>(`/api/v1/analytics/market-leaders?limit=${limit}`);
}
