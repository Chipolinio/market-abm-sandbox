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

/** Per-listing dense metrics (Slice 7.7). */
export type ListingMetricPoint = TickPoint & {
  price: number | null;
  gmv: number;
  volume: number;
};

export type ListingSeriesData = {
  listing_id: number;
  seller_id: number;
  points: ListingMetricPoint[];
};

export type ListingMetricKey = "price" | "gmv" | "volume";

/** Wide row for Recharts multi-line dense chart. */
export type ListingWideRow = {
  tick_id: number;
  [seriesKey: string]: number | null;
};

export type ListingMetricSeries = Map<number, ListingMetricPoint>;
