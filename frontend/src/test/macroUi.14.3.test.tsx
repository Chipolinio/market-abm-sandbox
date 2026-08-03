// Spec 014 §13.3 — RefPriceLine + EventCausalTooltip (slice 14.3).
// @vitest-environment jsdom
import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EventCausalTooltip } from "@/components/center/EventCausalTooltip";
import { RefPriceLine } from "@/components/center/RefPriceLine";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";
import { GmvChart } from "@/components/GmvChart";
import { extractDemandShockCausal } from "@/utils/demandShockCausal";

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
  Bar: () => null,
  ReferenceLine: (props: {
    y?: number;
    x?: number;
    label?: string | { value?: string };
    children?: ReactNode;
    onClick?: () => void;
  }) => {
    if (props.y !== undefined) {
      const label =
        typeof props.label === "string" ? props.label : (props.label?.value ?? "p50_hist");
      return (
        <div data-testid="ref-price-line" data-y={String(props.y)}>
          {label}
        </div>
      );
    }
    return (
      <div
        data-testid={`event-ref-line-${props.x}`}
        data-x={String(props.x)}
        onClick={props.onClick}
      >
        {props.children}
      </div>
    );
  },
  Label: ({ value }: { value?: string }) => <span>{value}</span>,
}));

afterEach(() => {
  cleanup();
});

describe("14.3 RefPriceLine", () => {
  it("price_chart_shows_ref_line", () => {
    render(
      <PriceQuantileChart
        data={[
          { tick_id: 1, p10: 9, p50: 10, p90: 11, mean_price: 10 },
          { tick_id: 2, p10: 8, p50: 9.5, p90: 11, mean_price: 9.5 },
        ]}
        refPrice={42.5}
      />,
    );
    const line = screen.getByTestId("ref-price-line");
    expect(line.getAttribute("data-y")).toBe("42.5");
    expect(line.textContent).toContain("p50_hist");
  });

  it("ref_price_line_hidden_when_null", () => {
    const { container } = render(<RefPriceLine refPrice={null} />);
    expect(container.querySelector("[data-testid='ref-price-line']")).toBeNull();

    render(
      <PriceQuantileChart
        data={[{ tick_id: 1, p10: 9, p50: 10, p90: 11, mean_price: 10 }]}
        refPrice={null}
      />,
    );
    expect(screen.queryByTestId("ref-price-line")).toBeNull();
  });
});

describe("14.3 EventCausalTooltip", () => {
  it("causal_tooltip_reads_payload_not_message", () => {
    const fromPayload = extractDemandShockCausal({
      impulse: 0.48,
      stress_after: 0.52,
      est_half_life_ticks: 28,
      scenario: "severe",
    });
    expect(fromPayload).not.toBeNull();
    expect(fromPayload!.impulse).toBe(0.48);
    expect(fromPayload!.stress_after).toBe(0.52);

    // Must not parse free-text message
    expect(
      extractDemandShockCausal(
        {},
        "Demand stress elevated (impulse=0.99, stress=0.88, est. half-life ~1 ticks).",
      ),
    ).toBeNull();

    render(
      <EventCausalTooltip
        causal={{
          impulse: 0.48,
          stress_after: 0.52,
          est_half_life_ticks: 28,
        }}
        onClose={() => undefined}
      />,
    );
    const tip = screen.getByTestId("event-causal-tooltip");
    expect(tip.textContent).toContain("0.48");
    expect(tip.textContent).toContain("0.52");
    expect(tip.textContent).toContain("28");
  });

  it("gmv_marker_click_opens_tooltip_from_payload", () => {
    render(
      <GmvChart
        data={[
          { tick_id: 5, gmv: 100, transaction_count: 2 },
          { tick_id: 10, gmv: 80, transaction_count: 1 },
        ]}
        eventMarkers={[
          {
            tickId: 10,
            label: "ШОК",
            payload: {
              impulse: 0.41,
              stress_after: 0.55,
              est_half_life_ticks: 22,
            },
          },
        ]}
      />,
    );
    fireEvent.click(screen.getByTestId("event-ref-line-10"));
    const tip = screen.getByTestId("event-causal-tooltip");
    expect(tip.textContent).toContain("0.41");
    expect(tip.textContent).toContain("0.55");
  });
});
