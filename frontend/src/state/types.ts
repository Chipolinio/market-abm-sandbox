/** Tiered ring-buffer class (Spec 007 §4.4). */
export type SeriesTier = "macro" | "dense";

/** Base telemetry point — strict key is tick_id. */
export type TickPoint = {
  tick_id: number;
  timestamp_utc?: string;
};

export type PriceTickPoint = TickPoint & {
  p10: number | null;
  p50: number | null;
  p90: number | null;
  mean_price: number | null;
};

export type GmvTickPoint = TickPoint & {
  gmv: number;
  transaction_count?: number;
};

/** Recharts row for price quantile chart. */
export type PriceChartRow = {
  tick_id: number;
  p10: number | null;
  p50: number | null;
  p90: number | null;
  mean_price: number | null;
};

export type TickSeries = Map<number, TickPoint>;
