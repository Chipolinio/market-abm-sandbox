// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TerminalTabs } from "@/components/center/TerminalTabs";

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

vi.mock("@/hooks/useMarketLeaders", () => ({
  useMarketLeaders: () => ({
    leaders: [],
    loading: false,
    error: null,
  }),
}));

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchSegmentHealth: vi.fn(async () => ({
      run_id: "r",
      tick_id: 0,
      rows: [],
    })),
    fetchCategoryRanking: vi.fn(async () => ({
      run_id: "r",
      tick_id: 0,
      rows: [],
    })),
    fetchDemandMatrix: vi.fn(async () => ({
      run_id: "r",
      tick_id: 0,
      grid_size: 3,
      row_count: 3,
      col_count: 3,
      x_labels: [],
      y_labels: [],
      axis_x: "strategy_type",
      axis_y: "pvd_segment",
      cells: [],
    })),
  };
});

const emptyDynamics = {
  priceChartData: [],
  gmvChartData: [],
  backfillLoading: false,
  backfillError: null,
};

afterEach(() => {
  cleanup();
});

describe("TerminalTabs", () => {
  it("mounts_only_active_panel", () => {
    const { rerender } = render(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={0}
        activeTab="dynamics"
        onTabChange={() => {}}
      />,
    );

    expect(screen.getByTestId("market-dynamics-panel")).toBeTruthy();
    expect(screen.queryByTestId("market-leaders-panel")).toBeNull();
    expect(screen.queryByTestId("demand-matrix-panel")).toBeNull();

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={0}
        activeTab="leaders"
        onTabChange={() => {}}
      />,
    );

    expect(screen.queryByTestId("market-dynamics-panel")).toBeNull();
    expect(screen.getByTestId("market-leaders-panel")).toBeTruthy();
    expect(screen.queryByTestId("demand-matrix-panel")).toBeNull();

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={0}
        activeTab="demand_matrix"
        onTabChange={() => {}}
      />,
    );

    expect(screen.queryByTestId("market-dynamics-panel")).toBeNull();
    expect(screen.queryByTestId("market-leaders-panel")).toBeNull();
    expect(screen.getByTestId("demand-matrix-panel")).toBeTruthy();
    expect(screen.queryByTestId("segment-health-panel")).toBeNull();

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={0}
        activeTab="segments"
        onTabChange={() => {}}
      />,
    );

    expect(screen.queryByTestId("market-dynamics-panel")).toBeNull();
    expect(screen.queryByTestId("demand-matrix-panel")).toBeNull();
    expect(screen.getByTestId("segment-health-panel")).toBeTruthy();
    expect(screen.queryByTestId("category-ranking-panel")).toBeNull();

    rerender(
      <TerminalTabs
        dynamics={emptyDynamics}
        asOfTick={0}
        activeTab="categories"
        onTabChange={() => {}}
      />,
    );

    expect(screen.queryByTestId("segment-health-panel")).toBeNull();
    expect(screen.getByTestId("category-ranking-panel")).toBeTruthy();
  });
});
