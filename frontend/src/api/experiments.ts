import { apiFetch } from "@/api/client";
import { apiBaseUrl } from "@/api/config";
import type { ExperimentSummaryResponse } from "@/types/experiments";

export async function fetchExperimentList(): Promise<string[]> {
  const body = await apiFetch<{ experiments: string[] }>("/api/v1/experiments");
  return body.experiments;
}

export async function fetchExperimentSummary(
  experimentId: string,
): Promise<ExperimentSummaryResponse> {
  return apiFetch<ExperimentSummaryResponse>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/summary`,
  );
}

export function experimentFigureUrl(experimentId: string, figureName: string): string {
  return `${apiBaseUrl()}/api/v1/experiments/${encodeURIComponent(experimentId)}/figures/${encodeURIComponent(figureName)}`;
}
