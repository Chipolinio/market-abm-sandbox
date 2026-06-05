// @vitest-environment jsdom
import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EMPTY_PRICE_MESSAGE, PriceQuantileChart } from "@/components/PriceQuantileChart";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ComposedChart: ({ children }: { children: ReactNode }) => <div data-testid="chart">{children}</div>,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Area: () => null,
  Line: () => null,
}));

describe("PriceQuantileChart", () => {
  it("renders_empty_state", () => {
    render(<PriceQuantileChart data={[]} />);
    expect(screen.getByText(EMPTY_PRICE_MESSAGE)).toBeTruthy();
  });
});
