// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "@/App";

vi.mock("@/hooks/useSimulationStatus", () => ({
  useSimulationStatus: () => ({
    status: { state: "IDLE", last_error: null },
    refresh: vi.fn(async () => ({ state: "IDLE" })),
  }),
}));

vi.mock("@/hooks/useDashboardSeries", () => ({
  useDashboardSeries: () => ({
    priceChartData: [],
    gmvChartData: [],
    totalGmv: 0,
    driftAlerts: [],
    backfillLoading: false,
    backfillError: null,
    handlePayload: vi.fn(),
    reloadBackfill: vi.fn(async () => undefined),
  }),
}));

vi.mock("@/hooks/useTopListingsSeries", () => ({
  useTopListingsSeries: (_enabled: boolean) => ({
    listings: [],
    loading: false,
    error: null,
    reload: vi.fn(async () => undefined),
  }),
}));

vi.mock("@/hooks/useTickStream", () => ({
  useTickStream: () => ({
    connectionState: "open",
    reconnectAttempt: 0,
    lastPayload: {
      tick_id: 7,
      timestamp_utc: "2026-06-06T00:00:00Z",
      market_summary: {
        mean_price: 1,
        total_gmv: 1000,
        total_transactions: 1,
        price_quantiles: null,
      },
      ticker_metrics: {
        active_sellers_count: 5,
        total_non_bankrupt_sellers: 10,
        total_market_gmv: 1000,
        market_price_index: 1.0,
        current_tick: 7,
      },
      active_drift_alerts: [],
      events: [],
      worker_state: "IDLE",
    },
  }),
}));

vi.mock("@/hooks/useCyberLog", () => ({
  useCyberLog: () => ({
    lines: [],
    loading: false,
    error: null,
  }),
}));

afterEach(() => {
  cleanup();
});

describe("App", () => {
  it("renders_trading_terminal_layout", () => {
    render(<App />);

    expect(screen.getByTestId("zone-left-sidebar")).toBeTruthy();
    expect(screen.getByTestId("zone-main")).toBeTruthy();
    expect(screen.getByTestId("zone-cyberlog")).toBeTruthy();
    expect(screen.getByText(/5\/10/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start" })).toBeTruthy();
  });
});
