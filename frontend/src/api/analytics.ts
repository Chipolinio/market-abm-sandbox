import { apiFetch } from "./client";
import type { GmvPoint, PriceIndexPoint } from "./types";

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
