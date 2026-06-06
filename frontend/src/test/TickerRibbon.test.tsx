// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TickerRibbon } from "@/components/header/TickerRibbon";
import type { TickerMetricsDTO } from "@/types/ticker";

afterEach(() => {
  cleanup();
});

const mockMetrics: TickerMetricsDTO = {
  active_sellers_count: 18,
  total_non_bankrupt_sellers: 25,
  total_market_gmv: 1_250_000,
  market_price_index: 1.03,
  current_tick: 42,
};

describe("TickerRibbon", () => {
  it("renders_four_metric_cards", () => {
    render(
      <TickerRibbon metrics={mockMetrics} connectionState="open" workerState="RUNNING" />,
    );

    expect(screen.getByText(/18\/25/)).toBeTruthy();
    expect(screen.getByText(/1\.3M/)).toBeTruthy();
    expect(screen.getByText(/1\.03/)).toBeTruthy();
    expect(screen.getByText(/t=\s*42/)).toBeTruthy();
    expect(screen.getAllByTestId("ticker-card")).toHaveLength(4);
  });

  it("shows_skeleton_when_metrics_null", () => {
    render(<TickerRibbon metrics={null} connectionState="open" workerState="IDLE" />);

    expect(screen.queryByText(/18\/25/)).toBeNull();
    expect(screen.queryByText(/GMV:/)).toBeNull();
    expect(screen.queryByText(/Index:/)).toBeNull();
    expect(screen.getAllByTestId("ticker-skeleton")).toHaveLength(4);
  });

  it.each([
    ["open", "bg-green-400"],
    ["connecting", "bg-amber-400"],
    ["error", "bg-red-400"],
    ["closed", "bg-slate-400"],
  ] as const)("connection_indicator_%s_uses_%s", (connectionState, expectedClass) => {
    render(
      <TickerRibbon metrics={mockMetrics} connectionState={connectionState} workerState="IDLE" />,
    );

    const dot = screen.getByTestId("connection-dot");
    expect(dot.className.split(/\s+/)).toContain(expectedClass);
  });
});
