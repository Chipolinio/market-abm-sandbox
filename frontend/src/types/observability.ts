/** Spec 014 §6–§7 analytics DTOs. */

export type SegmentRowDTO = {
  segment: "rich" | "standard" | "low";
  n_buyers: number;
  n_active: number;
  mean_budget_effective: number;
  mean_budget_baseline: number;
  mean_freq_effective: number;
  mean_scar_factor: number;
  churn_share: number;
};

export type SegmentHealthResponse = {
  run_id: string;
  tick_id: number;
  rows: SegmentRowDTO[];
};

export type StrategyPulseRowDTO = {
  strategy_type: string;
  avg_demand_index: number;
  n_listings: number;
};

export type StrategyPulseResponse = {
  run_id: string;
  tick_id: number;
  panic_active: boolean;
  strategies: StrategyPulseRowDTO[];
};

export type ListingRankingBreakdownDTO = {
  seller_id: number;
  listing_id: number;
  w1: number;
  w2: number;
  w3: number;
  rating: number;
  price_term: number;
  sales_term: number;
  term_rating: number;
  term_price: number;
  term_sales: number;
  score: number;
};

export type CategoryRankingRowDTO = {
  category_id: number;
  n_listings: number;
  median_score: number;
  median_price: number;
  sales_window_sum: number;
  top_listing_ids: number[];
};

export type CategoryRankingResponse = {
  run_id: string;
  tick_id: number;
  rows: CategoryRankingRowDTO[];
};
