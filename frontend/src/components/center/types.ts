import type { GmvTickPoint, PriceChartRow } from "@/state/types";

export type EventMarker = {
  tickId: number;
  label: string;
};

export type DynamicsTabProps = {
  priceChartData: PriceChartRow[];
  gmvChartData: GmvTickPoint[];
  backfillLoading?: boolean;
  backfillError?: string | null;
  highlightedSellerId?: number | null;
  crashMarkers?: EventMarker[];
};

export type TerminalTabId = "dynamics" | "leaders" | "demand_matrix";
