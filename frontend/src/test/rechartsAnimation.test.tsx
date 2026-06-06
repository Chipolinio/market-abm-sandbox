// @vitest-environment jsdom
import type { ReactNode } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { GmvChart } from "@/components/GmvChart";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";

const lineProps: Array<{ isAnimationActive?: boolean; dot?: boolean }> = [];
const areaProps: Array<{ isAnimationActive?: boolean; dot?: boolean }> = [];
const barProps: Array<{ isAnimationActive?: boolean }> = [];

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ComposedChart: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
  Line: (props: { isAnimationActive?: boolean; dot?: boolean }) => {
    lineProps.push(props);
    return null;
  },
  Area: (props: { isAnimationActive?: boolean; dot?: boolean }) => {
    areaProps.push(props);
    return null;
  },
  Bar: (props: { isAnimationActive?: boolean }) => {
    barProps.push(props);
    return null;
  },
}));

describe("recharts animation", () => {
  it("disables_animation_and_dots_on_market_dynamics_charts", () => {
    lineProps.length = 0;
    areaProps.length = 0;
    barProps.length = 0;

    render(
      <PriceQuantileChart
        data={[
          {
            tick_id: 1,
            p10: 10,
            p50: 20,
            p90: 30,
            mean_price: 20,
          },
        ]}
      />,
    );

    render(
      <GmvChart
        data={[
          {
            tick_id: 1,
            gmv: 100,
            transaction_count: 5,
          },
        ]}
      />,
    );

    expect(lineProps.length).toBeGreaterThan(0);
    expect(areaProps.length).toBeGreaterThan(0);
    expect(barProps.length).toBeGreaterThan(0);

    for (const props of [...lineProps, ...areaProps, ...barProps]) {
      expect(props.isAnimationActive).toBe(false);
    }

    for (const props of [...lineProps, ...areaProps]) {
      expect(props.dot).toBe(false);
    }
  });
});
