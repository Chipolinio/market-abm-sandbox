// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TopSellersDashboard } from "@/components/cyberlog/TopSellersDashboard";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const fetchMarketLeaders = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchMarketLeaders: (...args: unknown[]) => fetchMarketLeaders(...args),
  };
});

const mockSellers: MarketLeaderRowDTO[] = [
  {
    seller_id: 1,
    working_capital: 10_000,
    tick_revenue: 100,
    cumulative_revenue: 1_000,
    is_bankrupt: false,
    algorithm_type: "CB",
    inventory_stock: 15,
    logic_status: "roi_optimization",
  },
  {
    seller_id: 2,
    working_capital: 8_000,
    tick_revenue: 80,
    cumulative_revenue: 800,
    is_bankrupt: false,
    algorithm_type: "REPR",
    inventory_stock: 10,
    logic_status: "aggressive_dumping",
  },
  {
    seller_id: 3,
    working_capital: 6_000,
    tick_revenue: 60,
    cumulative_revenue: 600,
    is_bankrupt: false,
    algorithm_type: "RULE",
    inventory_stock: 7,
    logic_status: "rule_based",
  },
];

beforeEach(() => {
  fetchMarketLeaders.mockResolvedValue({
    run_id: "run-1",
    tick_id: 5,
    leaders: mockSellers,
  });
});

afterEach(() => {
  cleanup();
  fetchMarketLeaders.mockReset();
});

describe("TopSellersDashboard", () => {
  it("renders_three_seller_cards", async () => {
    render(
      <TopSellersDashboard
        asOfTick={5}
        highlightedSellerId={null}
        onHighlightSeller={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByTestId("top-seller-card")).toHaveLength(3);
    });
    expect(fetchMarketLeaders).toHaveBeenCalledWith(5, 3);
  });

  it("toggles_highlighted_seller_on_click", async () => {
    const onHighlight = vi.fn();
    render(
      <TopSellersDashboard
        asOfTick={5}
        highlightedSellerId={null}
        onHighlightSeller={onHighlight}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByTestId("top-seller-card")).toHaveLength(3);
    });

    fireEvent.click(screen.getAllByTestId("top-seller-card")[0]!);
    expect(onHighlight).toHaveBeenCalledWith(1);
  });
});
