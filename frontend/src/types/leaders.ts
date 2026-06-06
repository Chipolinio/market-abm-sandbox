/** Market leaders DTO (Spec 008 / Spec 009 §4.3). */

export type AlgorithmType = "CB" | "REPR" | "RULE";

export type LogicStatus =
  | "roi_optimization"
  | "aggressive_dumping"
  | "rule_based"
  | "bankrupt";

export type MarketLeaderRowDTO = {
  seller_id: number;
  working_capital: number;
  tick_revenue: number;
  cumulative_revenue: number;
  is_bankrupt: boolean;
  algorithm_type: AlgorithmType;
  inventory_stock: number;
  logic_status: LogicStatus;
};

export type MarketLeadersResponse = {
  run_id: string;
  tick_id: number;
  leaders: MarketLeaderRowDTO[];
};
