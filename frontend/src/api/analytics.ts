import { apiFetch } from "./client";
import type { DemandMatrixResponse } from "@/types/demandMatrix";
import type { SystemEventsResponse } from "@/types/events";
import type { LeaderRankBy, MarketLeadersResponse } from "@/types/leaders";
import type {
  CategoryRankingResponse,
  ListingRankingBreakdownDTO,
  SegmentHealthResponse,
  StrategyPulseResponse,
} from "@/types/observability";
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
  rankBy: LeaderRankBy = "tick_revenue",
): Promise<MarketLeadersResponse> {
  const params = new URLSearchParams({
    tick_id: String(tickId),
    limit: String(limit),
    rank_by: rankBy,
  });
  return apiFetch<MarketLeadersResponse>(`/api/v1/analytics/market-leaders?${params.toString()}`);
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

export function fetchSegmentHealth(tickId?: number): Promise<SegmentHealthResponse> {
  const params = new URLSearchParams();
  if (tickId !== undefined) {
    params.set("tick_id", String(tickId));
  }
  const qs = params.toString();
  return apiFetch<SegmentHealthResponse>(
    `/api/v1/analytics/segments${qs ? `?${qs}` : ""}`,
  );
}

export function fetchStrategyPulse(tickId?: number): Promise<StrategyPulseResponse> {
  const params = new URLSearchParams();
  if (tickId !== undefined) {
    params.set("tick_id", String(tickId));
  }
  const qs = params.toString();
  return apiFetch<StrategyPulseResponse>(
    `/api/v1/analytics/strategy-pulse${qs ? `?${qs}` : ""}`,
  );
}

export function fetchListingRanking(
  sellerId: number,
  tickId: number = 0,
): Promise<ListingRankingBreakdownDTO> {
  const params = new URLSearchParams({
    seller_id: String(sellerId),
    tick_id: String(tickId),
  });
  return apiFetch<ListingRankingBreakdownDTO>(
    `/api/v1/analytics/listing-ranking?${params.toString()}`,
  );
}

export function fetchCategoryRanking(tickId?: number): Promise<CategoryRankingResponse> {
  const params = new URLSearchParams();
  if (tickId !== undefined) {
    params.set("tick_id", String(tickId));
  }
  const qs = params.toString();
  return apiFetch<CategoryRankingResponse>(
    `/api/v1/analytics/category-ranking${qs ? `?${qs}` : ""}`,
  );
}
