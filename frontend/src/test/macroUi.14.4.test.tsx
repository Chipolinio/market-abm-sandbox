// Spec 014 §13.4 — StrategyPulseBar + RankingScoreBreakdown + SegmentHealthTab (slice 14.4).
// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RankingScoreBreakdown } from "@/components/center/RankingScoreBreakdown";
import { SegmentHealthTab } from "@/components/center/SegmentHealthTab";
import { StrategyPulseBar } from "@/components/center/StrategyPulseBar";
import type { StrategyPulseResponse } from "@/types/observability";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const pulseFixture: StrategyPulseResponse = {
  run_id: "r1",
  tick_id: 4,
  panic_active: true,
  strategies: [
    { strategy_type: "MaxProfit", avg_demand_index: 1.12, n_listings: 3 },
    { strategy_type: "MaxVolume", avg_demand_index: 0.9, n_listings: 2 },
    { strategy_type: "RatingMaximizer", avg_demand_index: 1.05, n_listings: 1 },
  ],
};

describe("14.4 StrategyPulseBar", () => {
  it("renders_three_strategies_and_panic_badge", () => {
    render(<StrategyPulseBar pulse={pulseFixture} />);
    expect(screen.getByTestId("strategy-pulse-MaxProfit")).toBeTruthy();
    expect(screen.getByTestId("strategy-pulse-MaxVolume")).toBeTruthy();
    expect(screen.getByTestId("strategy-pulse-RatingMaximizer")).toBeTruthy();
    expect(screen.getByTestId("strategy-panic-badge").textContent).toContain("PANIC");
    expect(screen.getByText(/DI 1.12/)).toBeTruthy();
  });

  it("empty_pulse_shows_placeholder", () => {
    render(<StrategyPulseBar pulse={null} />);
    expect(screen.getByText(/Нет strategy pulse/)).toBeTruthy();
  });
});

describe("14.4 RankingScoreBreakdown", () => {
  it("loads_breakdown_when_enabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          seller_id: 7,
          listing_id: 101,
          w1: 0.4,
          w2: 0.35,
          w3: 0.25,
          rating: 4.5,
          price_term: 1.0,
          sales_term: 2.0,
          term_rating: 1.8,
          term_price: 0.35,
          term_sales: 0.5,
          score: 2.65,
        }),
      })),
    );

    render(<RankingScoreBreakdown sellerId={7} tickId={3} enabled />);
    await waitFor(() => {
      expect(screen.getByTestId("ranking-score-breakdown").textContent).toContain(
        "Score = 0.40×Rating",
      );
    });
    expect(screen.getByTestId("ranking-score-breakdown").textContent).toMatch(/→\s*2\.650/);
  });

  it("hidden_when_not_enabled", () => {
    const { container } = render(
      <RankingScoreBreakdown sellerId={7} tickId={3} enabled={false} />,
    );
    expect(container.querySelector("[data-testid='ranking-score-breakdown']")).toBeNull();
  });
});

describe("14.4 SegmentHealthTab", () => {
  it("renders_three_segment_rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          run_id: "r1",
          tick_id: 2,
          rows: [
            {
              segment: "rich",
              n_buyers: 2,
              n_active: 2,
              mean_budget_effective: 115,
              mean_budget_baseline: 100,
              mean_freq_effective: 0.45,
              mean_scar_factor: 0.05,
              churn_share: 0,
            },
            {
              segment: "standard",
              n_buyers: 1,
              n_active: 1,
              mean_budget_effective: 80,
              mean_budget_baseline: 80,
              mean_freq_effective: 0.3,
              mean_scar_factor: 0.2,
              churn_share: 0,
            },
            {
              segment: "low",
              n_buyers: 3,
              n_active: 2,
              mean_budget_effective: 35,
              mean_budget_baseline: 50,
              mean_freq_effective: 0.1,
              mean_scar_factor: 0.4,
              churn_share: 0.33,
            },
          ],
        }),
      })),
    );

    render(<SegmentHealthTab asOfTick={2} />);
    await waitFor(() => {
      expect(screen.getByTestId("segment-row-rich")).toBeTruthy();
    });
    expect(screen.getByTestId("segment-row-standard")).toBeTruthy();
    expect(screen.getByTestId("segment-row-low")).toBeTruthy();
  });
});
