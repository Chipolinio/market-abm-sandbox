/** Mirrors backend Pydantic DTOs (Slice 7.1 / 8.3). */

import type { SystemEventDTO } from "@/types/events";
import type { TickerMetricsDTO } from "@/types/ticker";

export type WorkerState = "IDLE" | "RUNNING" | "PAUSED" | "STOPPED" | "FAILED";

export type PriceQuantiles = {
  p10: number;
  p50: number;
  p90: number;
};

export type MarketAggregate = {
  mean_price: number;
  total_gmv: number;
  total_transactions: number;
  price_quantiles: PriceQuantiles | null;
};

export type TickStreamPayload = {
  tick_id: number;
  timestamp_utc: string;
  market_summary: MarketAggregate;
  ticker_metrics?: TickerMetricsDTO | null;
  active_drift_alerts: Array<Record<string, unknown>>;
  events?: SystemEventDTO[];
  worker_state: WorkerState;
};

export type SimulationStatus = {
  run_id: string;
  state: WorkerState;
  current_tick: number;
  elapsed_time_seconds: number;
  last_error: string | null;
};

export type PriceIndexPoint = {
  tick_id: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  mean_price: number | null;
};

export type GmvPoint = {
  tick_id: number;
  gmv: number;
  transaction_count: number;
};

export type ListingMetricPoint = {
  tick_id: number;
  price: number | null;
  gmv: number;
  volume: number;
};

export type ListingSeries = {
  listing_id: number;
  seller_id: number;
  points: ListingMetricPoint[];
};

export type ApiErrorBody = {
  detail?: string | Array<{ msg: string }>;
};
