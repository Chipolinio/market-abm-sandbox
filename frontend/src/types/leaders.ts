/** Market leaders DTO (Spec 008 / Spec 009 §4.3). */

export type MarketLeaderRowDTO = {
  seller_id: number;
  working_capital: number;
  tick_revenue: number;
  cumulative_revenue: number;
  is_bankrupt: boolean;
};

export type MarketLeadersResponse = {
  run_id: string;
  tick_id: number;
  leaders: MarketLeaderRowDTO[];
};
