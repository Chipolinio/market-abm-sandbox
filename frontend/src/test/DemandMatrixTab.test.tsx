// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DemandMatrixGrid, DemandMatrixTab } from "@/components/center/DemandMatrixTab";
import { TerminalTabs } from "@/components/center/TerminalTabs";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";
import { buildMatrixColorScale, cellBackgroundColor } from "@/utils/demandMatrixCell";

const fetchDemandMatrix = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchDemandMatrix: (...args: unknown[]) => fetchDemandMatrix(...args),
  };
});

vi.mock("@/hooks/useTopListingsSeries", () => ({
  useTopListingsSeries: () => ({
    listings: [],
    loading: false,
    error: null,
    reload: vi.fn(async () => undefined),
  }),
}));

vi.mock("@/hooks/useStrategyPulse", () => ({
  useStrategyPulse: () => ({
    pulse: null,
    loading: false,
    error: null,
    refresh: vi.fn(async () => undefined),
  }),
}));

const X_LABELS = ["MaxProfit", "MaxVolume", "RatingMaximizer"];
const Y_LABELS = ["rich", "standard", "low"];

function buildCells(): DemandMatrixCellDTO[] {
  return Array.from({ length: 9 }, (_, index) => ({
    row: Math.floor(index / 3),
    col: index % 3,
    density: index === 0 ? 0.6 : index === 8 ? 0.4 : 0,
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
    grid_size: 3,
    row_count: 3,
    col_count: 3,
    x_labels: X_LABELS,
    y_labels: Y_LABELS,
    axis_x: "strategy_type",
    axis_y: "pvd_segment",
    cells: buildCells(),
  });
});

afterEach(() => {
  cleanup();
  fetchDemandMatrix.mockReset();
});

describe("DemandMatrixGrid", () => {
  it("empty_cells_are_transparent_filled_cells_use_corporate_blue", () => {
    const cellsData = [
      { row: 0, col: 0, density: 0 },
      { row: 0, col: 1, density: 0.8 },
    ];
    const scale = buildMatrixColorScale(cellsData.map((cell) => cell.density));

    render(
      <DemandMatrixGrid
        cells={cellsData}
        rowCount={3}
        colCount={3}
        xLabels={X_LABELS}
        yLabels={Y_LABELS}
      />,
    );

    const cells = screen.getAllByTestId("demand-matrix-cell");
    expect(cells[0]?.style.backgroundColor).toBe("transparent");
    expect(cells[1]?.style.backgroundColor).toBe(cellBackgroundColor(0.8, scale));
    expect(cells[1]?.textContent).toBe("80%");
  });

  it("renders_axis_labels", () => {
    render(
      <DemandMatrixGrid
        cells={[{ row: 0, col: 0, density: 0.5 }]}
        rowCount={3}
        colCount={3}
        xLabels={X_LABELS}
        yLabels={Y_LABELS}
      />,
    );

    expect(screen.getByText("CatBoost")).toBeTruthy();
    expect(screen.getByText("Лояльные к качеству")).toBeTruthy();
  });

  it("renders_relative_color_legend", () => {
    render(
      <DemandMatrixGrid
        cells={[{ row: 0, col: 0, density: 0.4 }]}
        rowCount={3}
        colCount={3}
        xLabels={X_LABELS}
        yLabels={Y_LABELS}
      />,
    );

    expect(screen.getByTestId("demand-matrix-legend").children).toHaveLength(5);
  });

  it("empty_cells_use_pale_border", () => {
    render(
      <DemandMatrixGrid
        cells={[{ row: 0, col: 0, density: 0 }]}
        rowCount={3}
        colCount={3}
        xLabels={X_LABELS}
        yLabels={Y_LABELS}
      />,
    );
    const cells = screen.getAllByTestId("demand-matrix-cell");
    expect(cells[0]?.className.split(/\s+/)).toContain("border-[#F1F5F9]");
    expect(cells[0]?.style.backgroundColor).toBe("transparent");
  });
});

describe("DemandMatrixTab", () => {
  it("renders_3x3_grid", async () => {
    render(<DemandMatrixTab asOfTick={5} />);

    await waitFor(() => {
      expect(screen.getAllByTestId("demand-matrix-cell")).toHaveLength(9);
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
