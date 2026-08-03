import type { GmvTickPoint, PriceChartRow } from "@/state/types";
import type { ActiveShockDTO, MacroStateDTO } from "@/types/macro";
import type { ConnectionState } from "@/types/ticker";
import type { WorkerState } from "@/api/types";

export type EventMarker = {
  tickId: number;
  label: string;
  /** Spec 014 — structured DEMAND_SHOCK payload for causal tooltip */
  payload?: Record<string, unknown> | null;
};

export type DynamicsTabProps = {
  priceChartData: PriceChartRow[];
  gmvChartData: GmvTickPoint[];
  backfillLoading?: boolean;
  backfillError?: string | null;
  highlightedSellerId?: number | null;
  crashMarkers?: EventMarker[];
  macroState?: MacroStateDTO | null;
  activeShocks?: ActiveShockDTO[];
  workerState?: WorkerState;
  connectionState?: ConnectionState;
  refPrice?: number | null;
  asOfTick?: number;
  pollStrategyPulse?: boolean;
};

export type TerminalTabId =
  | "dynamics"
  | "leaders"
  | "demand_matrix"
  | "segments"
  | "categories";
