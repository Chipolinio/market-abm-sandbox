// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResearchLab } from "@/pages/ResearchLab";

const postExperimentRun = vi.fn();
const fetchCurrentJob = vi.fn();
const fetchJob = vi.fn();
const fetchExperimentSummary = vi.fn();

vi.mock("@/api/experiments", () => ({
  postExperimentRun: (...args: unknown[]) => postExperimentRun(...args),
  fetchCurrentJob: (...args: unknown[]) => fetchCurrentJob(...args),
  fetchJob: (...args: unknown[]) => fetchJob(...args),
  fetchExperimentSummary: (...args: unknown[]) => fetchExperimentSummary(...args),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("15.7 ResearchLab launch", () => {
  it("15.7-T5 paper confirm cancel does not POST; ok does POST", async () => {
    fetchCurrentJob.mockResolvedValue({ job: null });
    postExperimentRun.mockResolvedValue({
      job_id: "job_1",
      experiment_id: "exp_paper",
      status: "RUNNING",
    });

    const confirmFn = vi.fn().mockReturnValue(false);
    render(<ResearchLab confirmFn={confirmFn} />);
    await waitFor(() => expect(fetchCurrentJob).toHaveBeenCalled());

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "paper" } });
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    expect(confirmFn).toHaveBeenCalled();
    expect(postExperimentRun).not.toHaveBeenCalled();

    confirmFn.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));
    await waitFor(() => expect(postExperimentRun).toHaveBeenCalledTimes(1));
  });

  it("15.7-T6 mount resumes poll when current job RUNNING", async () => {
    fetchCurrentJob.mockResolvedValue({
      job: {
        job_id: "job_running",
        experiment_id: "exp_smoke_1",
        status: "RUNNING",
        done: 1,
        total: 6,
      },
    });
    fetchJob.mockResolvedValue({
      job_id: "job_running",
      experiment_id: "exp_smoke_1",
      status: "RUNNING",
      done: 2,
      total: 6,
    });

    render(<ResearchLab pollIntervalMs={50} />);
    await waitFor(() =>
      expect(screen.getByTestId("job-status").textContent).toMatch(/Выполняется/),
    );
    await waitFor(() => expect(fetchJob).toHaveBeenCalled(), { timeout: 2000 });
  });

  it("renders results table from loaded summary after DONE path", async () => {
    fetchCurrentJob.mockResolvedValue({
      job: {
        job_id: "job_done",
        experiment_id: "paper_grid_v1",
        status: "DONE",
        done: 2,
        total: 2,
      },
    });
    fetchExperimentSummary.mockResolvedValue({
      experiment_id: "paper_grid_v1",
      rows: [
        {
          metric: "median_price",
          ml_share: 0,
          window: "post_burn_in",
          mean: 12.5,
          lo: 11,
          hi: 14,
        },
      ],
    });

    render(<ResearchLab />);
    await waitFor(() => expect(screen.getByText("12.5")).toBeTruthy());
    expect(screen.getByText("Медианная цена")).toBeTruthy();
    expect(screen.getByText("после прогрева")).toBeTruthy();
    expect(screen.getAllByText(/paper_grid_v1/).length).toBeGreaterThan(0);
  });
});
