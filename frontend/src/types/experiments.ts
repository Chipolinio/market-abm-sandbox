/** Spec 015 — experiment aggregate row (thin client mirror of summary.json). */
export type ExperimentSummaryRow = {
  metric: string;
  ml_share: number;
  window: string;
  mean: number;
  lo: number;
  hi: number;
  std?: number;
  n_runs?: number;
};

export type ExperimentSummaryResponse = {
  experiment_id: string;
  rows: ExperimentSummaryRow[];
};
