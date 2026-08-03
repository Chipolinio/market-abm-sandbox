/** Spec 014 — macro WS DTO mirrors (MacroStateDTO / ActiveShockDTO). */

export type MacroRegime = "normal" | "stress" | "expansion" | "recovery";

export type MacroStateDTO = {
  regime: MacroRegime;
  stress: number;
  expansion: number;
  stress_cap: number;
  expansion_cap: number;
  episode_id: number;
  ticks_in_episode: number;
  peak_stress: number;
  peak_expansion: number;
  est_recovery_eta_ticks: number | null;
};

export type ShockScenario = "mild" | "standard" | "severe";

export type ActiveShockDTO = {
  shock_type: string;
  intensity: number;
  remaining_ticks: number | null;
  applied_at_tick: number;
  scenario: ShockScenario | null;
};
