// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DemandMatrixTab } from "@/components/center/DemandMatrixTab";
import { TerminalTabs } from "@/components/center/TerminalTabs";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";

const fetchDemandMatrix = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchDemandMatrix: (...args: unknown[]) => fetchDemandMatrix(...args),
  };
});

function buildCells(): DemandMatrixCellDTO[] {
  return Array.from({ length: 100 }, (_, index) => ({
    row: Math.floor(index / 10),
    col: index % 10,
    density: (index % 10) / 10,
  }));
}

const emptyDynamics = {
  priceChartData: [],
  gmvChartData: [],
  topListings: [],
  topListingsLoading: false,
};

beforeEach(() => {
  fetchDemandMatrix.mockResolvedValue({
    run_id: "run-1",
    tick_id: 5,
    grid_size: 10,
    cells: buildCells(),
  });
});

afterEach(() => {
  cleanup();
  fetchDemandMatrix.mockReset();
});

describe("DemandMatrixTab", () => {
  it("renders_10x10_grid", async () => {
    render(<DemandMatrixTab />);

    await waitFor(() => {
      expect(screen.getAllByTestId("demand-matrix-cell")).toHaveLength(100);
    });
    expect(screen.getByTestId("demand-matrix-grid")).toBeTruthy();
  });

  it("fetches_on_tab_focus_only", async () => {
    const { rerender } = render(
      <TerminalTabs dynamics={emptyDynamics} activeTab="dynamics" onTabChange={() => {}} />,
    );

    expect(fetchDemandMatrix).not.toHaveBeenCalled();

    rerender(
      <TerminalTabs dynamics={emptyDynamics} activeTab="demand_matrix" onTabChange={() => {}} />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
    });

    rerender(
      <TerminalTabs dynamics={emptyDynamics} activeTab="dynamics" onTabChange={() => {}} />,
    );

    rerender(
      <TerminalTabs dynamics={emptyDynamics} activeTab="demand_matrix" onTabChange={() => {}} />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(2);
    });
  });
});
