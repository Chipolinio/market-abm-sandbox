/** Mirrors backend TickerMetricsDTO (Spec 008 §6.5). */

import type { WorkerState } from "@/api/types";

export type TickerMetricsDTO = {
  active_sellers_count: number;
  total_non_bankrupt_sellers: number;
  total_market_gmv: number;
  market_price_index: number;
  current_tick: number;
};

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type TickerRibbonProps = {
  metrics: TickerMetricsDTO | null;
  connectionState: ConnectionState;
  workerState: WorkerState;
};
