import type { GmvTickPoint, ListingSeriesData, PriceChartRow } from "@/state/types";

export type DynamicsTabProps = {
  priceChartData: PriceChartRow[];
  gmvChartData: GmvTickPoint[];
  topListings: ListingSeriesData[];
  topListingsLoading: boolean;
  backfillLoading?: boolean;
  backfillError?: string | null;
};

export type TerminalTabId = "dynamics" | "leaders" | "demand_matrix";
