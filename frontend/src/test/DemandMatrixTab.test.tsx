// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DemandMatrixGrid, DemandMatrixTab } from "@/components/center/DemandMatrixTab";
import { TerminalTabs } from "@/components/center/TerminalTabs";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";
import { DEMAND_MATRIX_MIN_OPACITY } from "@/utils/demandMatrixCell";

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
    density: index === 0 ? 0 : (index % 10) / 10,
  }));
}

const emptyDynamics = {
  priceChartData: [],
  gmvChartData: [],
  backfillLoading: false,
  backfillError: null,
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

describe("DemandMatrixGrid", () => {
  it("applies_min_opacity_for_zero_density_cells", () => {
    render(
      <DemandMatrixGrid
        cells={[
          { row: 0, col: 0, density: 0 },
          { row: 0, col: 1, density: 0.8 },
        ]}
      />,
    );

    const cells = screen.getAllByTestId("demand-matrix-cell");
    expect(cells[0]?.style.opacity).toBe(String(DEMAND_MATRIX_MIN_OPACITY));
    expect(cells[1]?.style.opacity).toBe("0.8");
  });
});

describe("DemandMatrixTab", () => {
  it("renders_10x10_grid", async () => {
    render(<DemandMatrixTab asOfTick={5} />);

    await waitFor(() => {
      expect(screen.getAllByTestId("demand-matrix-cell")).toHaveLength(100);
    });
    expect(screen.getByTestId("demand-matrix-grid")).toBeTruthy();
  });

  it("shows_loading_state", () => {
    fetchDemandMatrix.mockImplementation(
      () => new Promise(() => undefined),
    );

    render(<DemandMatrixTab asOfTick={5} />);
    expect(screen.getByText(/Загрузка матрицы/)).toBeTruthy();
  });

  it("shows_error_state", async () => {
    fetchDemandMatrix.mockRejectedValue(new Error("network error"));

    render(<DemandMatrixTab asOfTick={5} />);

    await waitFor(() => {
      expect(screen.getByText("network error")).toBeTruthy();
    });
  });

  it("fetches_on_tab_focus_only", async () => {
    const { rerender } = render(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={5}
        activeTab="dynamics"
        onTabChange={() => {}}
      />,
    );

    expect(fetchDemandMatrix).not.toHaveBeenCalled();

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={5}
        activeTab="demand_matrix"
        onTabChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
      expect(fetchDemandMatrix).toHaveBeenCalledWith(5);
    });

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={5}
        activeTab="dynamics"
        onTabChange={() => {}}
      />,
    );

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={5}
        activeTab="demand_matrix"
        onTabChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(2);
    });
  });

  it("does_not_refetch_while_tab_stays_open_and_tick_advances", async () => {
    const { rerender } = render(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={5}
        activeTab="demand_matrix"
        onTabChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
    });

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={42}
        activeTab="demand_matrix"
        onTabChange={() => {}}
      />,
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
    });
  });
});
