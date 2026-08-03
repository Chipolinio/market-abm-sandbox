import { apiFetch } from "@/api/client";
import { apiBaseUrl } from "@/api/config";
import type {
  CurrentJobResponse,
  ExperimentRunAccepted,
  ExperimentRunRequest,
  ExperimentSummaryResponse,
  JobStatus,
} from "@/types/experiments";

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

export async function fetchExperimentFigures(experimentId: string): Promise<string[]> {
  const body = await apiFetch<{ experiment_id: string; figures: string[] }>(
    `/api/v1/experiments/${encodeURIComponent(experimentId)}/figures`,
  );
  return body.figures;
}

export function experimentFigureUrl(experimentId: string, figureName: string): string {
  return `${apiBaseUrl()}/api/v1/experiments/${encodeURIComponent(experimentId)}/figures/${encodeURIComponent(figureName)}`;
}

export async function postExperimentRun(
  body: ExperimentRunRequest,
): Promise<ExperimentRunAccepted> {
  return apiFetch<ExperimentRunAccepted>("/api/v1/experiments/run", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function fetchCurrentJob(): Promise<CurrentJobResponse> {
  return apiFetch<CurrentJobResponse>("/api/v1/experiments/jobs/current");
}

export async function fetchJob(jobId: string): Promise<JobStatus> {
  return apiFetch<JobStatus>(`/api/v1/experiments/jobs/${encodeURIComponent(jobId)}`);
}
