/** Shock command DTO (Spec 009 §3.2). */

export type SimulationShockRequest = {
  shock_type:
    | "demand_crash"
    | "demand_boom"
    | "platform_fee_hike"
    | "platform_fee_cut"
    | "marketplace_promotion"
    | "supply_shock";
  intensity: number;
  duration_ticks: number;
};

export type SimulationShockResponse = {
  status: "queued";
  shock_type: string;
  queue_depth: number;
};
