/** Mirrors backend TickerMetricsDTO (Spec 008 §6.5). */

import type { WorkerState } from "@/api/types";
import type { MacroRegime } from "@/types/macro";

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
  /** UI-only delta vs previous WS frame (Spec 009 §2.5 Card 3). */
  priceIndexDelta?: number;
  /** UI-only alarm from FLASH_CRASH events (Spec 009 §2.5 Card 4). */
  flashCrashActive?: boolean;
  /** Spec 014 — macro regime pill */
  macroRegime?: MacroRegime | null;
};
