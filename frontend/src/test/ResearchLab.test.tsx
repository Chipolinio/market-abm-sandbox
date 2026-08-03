// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResearchLab } from "@/pages/ResearchLab";

const postExperimentRun = vi.fn();
const fetchCurrentJob = vi.fn();
const fetchJob = vi.fn();
const fetchExperimentSummary = vi.fn();
const fetchExperimentList = vi.fn();

vi.mock("@/api/experiments", () => ({
  postExperimentRun: (...args: unknown[]) => postExperimentRun(...args),
  fetchCurrentJob: (...args: unknown[]) => fetchCurrentJob(...args),
  fetchJob: (...args: unknown[]) => fetchJob(...args),
  fetchExperimentSummary: (...args: unknown[]) => fetchExperimentSummary(...args),
  fetchExperimentList: (...args: unknown[]) => fetchExperimentList(...args),
  experimentFigureUrl: (id: string, name: string) =>
    `http://test/api/v1/experiments/${id}/figures/${name}`,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("15.7 ResearchLab launch", () => {
  it("15.7-T5 paper confirm cancel does not POST; ok does POST", async () => {
    fetchCurrentJob.mockResolvedValue({ job: null });
    fetchExperimentList.mockResolvedValue([]);
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
    const paperBody = postExperimentRun.mock.calls[0][0] as { experiment_id: string };
    expect(paperBody.experiment_id).toBe("paper-1");
  });

  it("15.7-T6 mount resumes poll when current job RUNNING", async () => {
    fetchExperimentList.mockResolvedValue([]);
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
    fetchExperimentList.mockResolvedValue(["paper_grid_v1"]);
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
      figures: ["F1.png", "F2.png"],
      warnings: ["ml_registry=research_stub"],
      rows: [
        {
          metric: "median_price",
          ml_share: 0,
          window: "post_burn_in",
          mean: 12.5,
          lo: 11,
          hi: 14,
          median: 12.0,
          q25: 11.5,
          q75: 12.8,
        },
      ],
    });

    render(<ResearchLab />);
    await waitFor(() => expect(screen.getByText("Медианная цена")).toBeTruthy());
    expect(screen.getByText("после прогрева")).toBeTruthy();
    expect(screen.getAllByText(/paper_grid_v1/).length).toBeGreaterThan(0);
    await waitFor(() =>
      expect(screen.getByTestId("figure-gallery").querySelectorAll("img").length).toBe(2),
    );
    expect(screen.getByText(/ml_registry=research_stub/)).toBeTruthy();
    expect(screen.getByTestId("past-experiments").textContent).toMatch(/paper_grid_v1/);
  });

  it("auto-names smoke-N / paper-N from past list; opening past keeps launch id", async () => {
    fetchExperimentList.mockResolvedValue(["smoke-1", "smoke-2", "paper_grid_v1"]);
    fetchCurrentJob.mockResolvedValue({ job: null });
    fetchExperimentSummary.mockResolvedValue({
      experiment_id: "smoke-1",
      figures: ["F1.png"],
      warnings: [],
      rows: [
        {
          metric: "hhi",
          ml_share: 0,
          window: "full",
          mean: 1000,
          lo: 900,
          hi: 1100,
          median: 1000,
          q25: 950,
          q75: 1050,
        },
      ],
    });

    render(<ResearchLab />);
    await waitFor(() => {
      const input = screen.getByLabelText(/ID эксперимента/) as HTMLInputElement;
      expect(input.value).toBe("smoke-3");
    });

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "paper" } });
    await waitFor(() => {
      expect((screen.getByLabelText(/ID эксперимента/) as HTMLInputElement).value).toBe(
        "paper-1",
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "smoke-1" }));
    await waitFor(() => expect(fetchExperimentSummary).toHaveBeenCalledWith("smoke-1"));
    await waitFor(() => expect(screen.getByAltText(/F1/)).toBeTruthy());
    // Launch field stays on next free paper id
    expect((screen.getByLabelText(/ID эксперимента/) as HTMLInputElement).value).toBe("paper-1");
  });

  it("opens past experiment from list", async () => {
    fetchExperimentList.mockResolvedValue(["exp_old"]);
    fetchCurrentJob.mockResolvedValue({ job: null });
    fetchExperimentSummary.mockResolvedValue({
      experiment_id: "exp_old",
      figures: ["F1.png"],
      warnings: [],
      rows: [
        {
          metric: "hhi",
          ml_share: 1,
          window: "full",
          mean: 2000,
          lo: 1900,
          hi: 2100,
          median: 1990,
          q25: 1950,
          q75: 2050,
        },
      ],
    });

    render(<ResearchLab />);
    await waitFor(() => expect(screen.getByText("exp_old")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "exp_old" }));
    await waitFor(() => expect(fetchExperimentSummary).toHaveBeenCalledWith("exp_old"));
    await waitFor(() => expect(screen.getByText("HHI")).toBeTruthy());
    expect(screen.getByAltText(/F1/)).toBeTruthy();
  });

  it("custom preset exposes editable params and POSTs edited grid", async () => {
    fetchExperimentList.mockResolvedValue([]);
    fetchCurrentJob.mockResolvedValue({ job: null });
    postExperimentRun.mockResolvedValue({
      job_id: "job_custom",
      experiment_id: "exp_custom",
      status: "RUNNING",
    });

    render(<ResearchLab />);
    await waitFor(() => expect(fetchCurrentJob).toHaveBeenCalled());

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "custom" } });
    expect(screen.getByTestId("custom-params")).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/Сетка долей ML/), {
      target: { value: "0, 0.5, 1" },
    });
    fireEvent.change(screen.getByLabelText(/Прогонов на долю/), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Запустить" }));

    await waitFor(() => expect(postExperimentRun).toHaveBeenCalledTimes(1));
    const body = postExperimentRun.mock.calls[0][0] as {
      ml_share_grid: number[];
      n_runs: number;
      preset: string;
    };
    expect(body.preset).toBe("custom");
    expect(body.ml_share_grid).toEqual([0, 0.5, 1]);
    expect(body.n_runs).toBe(2);
  });
});
