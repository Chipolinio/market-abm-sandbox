import { apiFetch } from "./client";
import type { SimulationStatus, WorkerState } from "./types";

type CommandResponse = { state: string; message: string };

export type StartOptions = {
  run_id?: string | null;
  n_buyers?: number;
  n_sellers?: number;
  repricing_mode?: "rules" | "catboost" | "hybrid";
  force_clear?: boolean;
};

export function fetchSimulationStatus(): Promise<SimulationStatus> {
  return apiFetch<SimulationStatus>("/api/v1/simulation/status");
}

export function startSimulation(options: StartOptions = {}): Promise<CommandResponse> {
  return apiFetch<CommandResponse>("/api/v1/simulation/start", {
    method: "POST",
    body: JSON.stringify(options),
  });
}

export function pauseSimulation(): Promise<CommandResponse> {
  return apiFetch<CommandResponse>("/api/v1/simulation/pause", { method: "POST" });
}

export function stepSimulation(): Promise<CommandResponse> {
  return apiFetch<CommandResponse>("/api/v1/simulation/step", { method: "POST" });
}

export function resetSimulation(): Promise<CommandResponse> {
  return apiFetch<CommandResponse>("/api/v1/simulation/reset", { method: "POST" });
}

export function isTerminalState(state: WorkerState): boolean {
  return state === "STOPPED" || state === "FAILED";
}
