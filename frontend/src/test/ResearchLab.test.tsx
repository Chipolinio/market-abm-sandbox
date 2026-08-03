// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ResearchLab } from "@/pages/ResearchLab";
import type { ExperimentSummaryRow } from "@/types/experiments";

const FIXTURE: ExperimentSummaryRow[] = [
  {
    metric: "median_price",
    ml_share: 0,
    window: "post_burn_in",
    mean: 12.5,
    lo: 11,
    hi: 14,
    std: 1,
    n_runs: 3,
  },
  {
    metric: "hhi",
    ml_share: 0.5,
    window: "post_burn_in",
    mean: 1500,
    lo: 1400,
    hi: 1600,
    std: 50,
    n_runs: 3,
  },
];

afterEach(() => {
  cleanup();
});

describe("15.6-T2 research_page_renders_from_summary", () => {
  it("renders mean fields from fixture JSON (thin client)", () => {
    render(
      <ResearchLab experimentId="paper_grid_v1" summaryRows={FIXTURE} />,
    );
    expect(screen.getByText(/Research Lab/i)).toBeTruthy();
    expect(screen.getByText(/paper_grid_v1/)).toBeTruthy();
    expect(screen.getByText(/median_price/)).toBeTruthy();
    expect(screen.getByText("12.5")).toBeTruthy();
    expect(screen.getByText(/hhi/i)).toBeTruthy();
    expect(screen.getByText("1500")).toBeTruthy();
  });
});
