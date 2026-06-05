// @vitest-environment jsdom
import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TopListingsSection } from "../components/TopListingsSection";
import type { ListingSeriesData } from "../state/types";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: ({ children }: { children: ReactNode }) => <div data-testid="dense-chart">{children}</div>,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Line: () => null,
}));

const listings: ListingSeriesData[] = [
  {
    listing_id: 0,
    seller_id: 1,
    points: [{ tick_id: 0, price: 100, gmv: 50, volume: 2 }],
  },
];

describe("TopListingsSection", () => {
  it("renders_loading_state", () => {
    render(<TopListingsSection listings={[]} loading />);
    expect(screen.getByText(/Loading top listings/i)).toBeTruthy();
  });

  it("renders_empty_state_without_data", () => {
    render(<TopListingsSection listings={[]} loading={false} />);
    expect(screen.getByText(/No listing data yet/i)).toBeTruthy();
  });

  it("renders_dense_metric_titles_when_data_present", () => {
    render(<TopListingsSection listings={listings} loading={false} />);
    expect(screen.getByText(/Price by listing/i)).toBeTruthy();
    expect(screen.getByText(/GMV by listing/i)).toBeTruthy();
    expect(screen.getByText(/Volume by listing/i)).toBeTruthy();
  });
});
