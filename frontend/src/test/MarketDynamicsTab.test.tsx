// @vitest-environment jsdom
import type { ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketDynamicsTab } from "@/components/center/MarketDynamicsTab";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ComposedChart: ({ children }: { children: ReactNode }) => <div data-testid="composed-chart">{children}</div>,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Line: () => null,
  Area: () => null,
  Bar: () => null,
  ReferenceLine: () => null,
  Label: () => null,
}));

vi.mock("@/hooks/useTopListingsSeries", () => ({
  useTopListingsSeries: () => ({
    listings: [
      {
        listing_id: 101,
        seller_id: 7,
        points: [
          { tick_id: 1, price: 10, gmv: 0, volume: 0 },
          { tick_id: 2, price: 9.5, gmv: 0, volume: 0 },
        ],
      },
    ],
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

afterEach(() => {
  cleanup();
});

describe("MarketDynamicsTab", () => {
  it("renders_price_and_gmv_sections", () => {
    render(
      <MarketDynamicsTab
        priceChartData={[
          { tick_id: 1, p10: 9, p50: 10, p90: 11, mean_price: 10 },
          { tick_id: 2, p10: 8, p50: 9, p90: 10, mean_price: 9 },
        ]}
        gmvChartData={[
          { tick_id: 1, gmv: 100, transaction_count: 2 },
          { tick_id: 2, gmv: 150, transaction_count: 3 },
        ]}
      />,
    );

    expect(screen.getByTestId("market-dynamics-panel")).toBeTruthy();
    expect(screen.getByText(/Квантили цен/)).toBeTruthy();
    expect(screen.getByText(/GMV по тикам/)).toBeTruthy();
    expect(screen.getAllByTestId("composed-chart")).toHaveLength(2);
  });

  it("shows_backfill_loading_state", () => {
    render(
      <MarketDynamicsTab
        priceChartData={[]}
        gmvChartData={[]}
        backfillLoading
      />,
    );

    expect(screen.getByText(/Загрузка истории/)).toBeTruthy();
  });

  it("shows_backfill_error", () => {
    render(
      <MarketDynamicsTab
        priceChartData={[]}
        gmvChartData={[]}
        backfillError="network error"
      />,
    );

    expect(screen.getByText(/Backfill: network error/)).toBeTruthy();
  });

  it("shows_highlight_banner_for_selected_seller", () => {
    render(
      <MarketDynamicsTab
        priceChartData={[
          { tick_id: 1, p10: 9, p50: 10, p90: 11, mean_price: 10 },
          { tick_id: 2, p10: 8, p50: 9, p90: 10, mean_price: 9 },
        ]}
        gmvChartData={[{ tick_id: 1, gmv: 100, transaction_count: 2 }]}
        highlightedSellerId={7}
        crashMarkers={[{ tickId: 2, label: "CRASH" }]}
      />,
    );

    expect(screen.getByText(/Seller #7 price/)).toBeTruthy();
  });
});
