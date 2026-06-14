/** Shock command DTO (Spec 009 §3.2 / Spec 011 §8.4). */

export type CrisisScenario = "mild" | "standard" | "severe";

export type SimulationShockRequest = {
  shock_type:
    | "demand_crash"
    | "demand_boom"
    | "platform_fee_hike"
    | "platform_fee_cut"
    | "marketplace_promotion"
    | "supply_shock";
  intensity: number;
  duration_ticks?: number | null;
  scenario?: CrisisScenario | null;
  shock_mode?: "stochastic_regime" | "fixed_duration" | null;
};

export type SimulationShockResponse = {
  status: "queued";
  shock_type: string;
  queue_depth: number;
};
