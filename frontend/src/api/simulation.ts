import { apiFetch } from "./client";
import type { SessionConfigureRequest, SessionConfigureResponse } from "@/types/session";
import type { SimulationShockRequest, SimulationShockResponse } from "@/types/shock";
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

export function configureSession(body: SessionConfigureRequest): Promise<SessionConfigureResponse> {
  return apiFetch<SessionConfigureResponse>("/api/v1/simulation/configure", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function triggerShock(body: SimulationShockRequest): Promise<SimulationShockResponse> {
  return apiFetch<SimulationShockResponse>("/api/v1/simulation/shock", {
    method: "POST",
    body: JSON.stringify(body),
  });
}
