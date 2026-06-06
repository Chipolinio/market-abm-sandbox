import type { GmvTickPoint, PriceChartRow } from "@/state/types";

export type DynamicsTabProps = {
  priceChartData: PriceChartRow[];
  gmvChartData: GmvTickPoint[];
  backfillLoading?: boolean;
  backfillError?: string | null;
};

export type TerminalTabId = "dynamics" | "leaders" | "demand_matrix";
