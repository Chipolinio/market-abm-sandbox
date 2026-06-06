// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TerminalTabs } from "@/components/center/TerminalTabs";

const emptyDynamics = {
  priceChartData: [],
  gmvChartData: [],
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
  });
});
