/** Spec 015 / 015.1 — experiment DTOs. */
export type ExperimentSummaryRow = {
  metric: string;
  ml_share: number;
  window: string;
  mean: number;
  lo: number;
  hi: number;
  median?: number;
  q25?: number;
  q75?: number;
  std?: number;
  n_runs?: number;
};

export type ExperimentSummaryResponse = {
  experiment_id: string;
  rows: ExperimentSummaryRow[];
  warnings?: string[];
  figures?: string[];
};

export type ExperimentPreset = "smoke" | "paper" | "custom";

export type ExperimentRunRequest = {
  experiment_id: string;
  preset: ExperimentPreset;
  ml_share_grid: number[];
  n_runs: number;
  n_ticks: number;
  burn_in_ticks: number;
  jobs: number;
  runtime_mode: "legacy" | "extended";
  n_buyers: number;
  n_sellers: number;
  base_seed: number;
};

export type ExperimentRunAccepted = {
  job_id: string;
  experiment_id: string;
  status: string;
};

export type JobStatus = {
  job_id: string;
  experiment_id: string;
  status: "QUEUED" | "RUNNING" | "DONE" | "FAILED" | string;
  done: number;
  total: number;
  current_ml_share?: number | null;
  current_run_index?: number | null;
  error?: string | null;
  warnings?: string[];
  started_at?: string | null;
  finished_at?: string | null;
};

export type CurrentJobResponse = {
  job: JobStatus | null;
};

export const SMOKE_PRESET: Omit<ExperimentRunRequest, "experiment_id"> = {
  preset: "smoke",
  ml_share_grid: [0, 1],
  n_runs: 3,
  n_ticks: 20,
  burn_in_ticks: 0,
  jobs: 2,
  runtime_mode: "legacy",
  n_buyers: 80,
  // Fine share grids need enough sellers; 8 made mid-shares bit-identical under monopoly.
  n_sellers: 40,
  base_seed: 10000,
};

export const PAPER_PRESET: Omit<ExperimentRunRequest, "experiment_id"> = {
  preset: "paper",
  ml_share_grid: [0, 0.25, 0.5, 0.75, 1],
  n_runs: 30,
  n_ticks: 500,
  burn_in_ticks: 100,
  jobs: 2,
  runtime_mode: "legacy",
  n_buyers: 200,
  n_sellers: 50,
  base_seed: 10000,
};
