// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SELLERS_REGISTRY_LIMIT } from "@/api/analytics";
import { MarketLeadersTab } from "@/components/center/MarketLeadersTab";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const useMarketLeaders = vi.fn();

vi.mock("@/hooks/useMarketLeaders", () => ({
  useMarketLeaders: (...args: unknown[]) => useMarketLeaders(...args),
}));

const mockLeaders: MarketLeaderRowDTO[] = [
  {
    seller_id: 3,
    working_capital: 9_500.5,
    tick_revenue: 120.25,
    cumulative_revenue: 4_200.0,
    is_bankrupt: false,
    algorithm_type: "CB",
    inventory_stock: 12,
    logic_status: "roi_optimization",
  },
  {
    seller_id: 1,
    working_capital: 7_100.0,
    tick_revenue: 80.0,
    cumulative_revenue: 3_100.5,
    is_bankrupt: false,
    algorithm_type: "REPR",
    inventory_stock: 8,
    logic_status: "aggressive_dumping",
  },
  {
    seller_id: 7,
    working_capital: 5_000.0,
    tick_revenue: 0.0,
    cumulative_revenue: 1_800.0,
    is_bankrupt: true,
    algorithm_type: "RULE",
    inventory_stock: 0,
    logic_status: "bankrupt",
  },
];

beforeEach(() => {
  useMarketLeaders.mockReturnValue({
    leaders: mockLeaders,
    loading: false,
    error: null,
  });
});

afterEach(() => {
  cleanup();
  useMarketLeaders.mockReset();
});

describe("MarketLeadersTab", () => {
  it("requests_full_seller_registry", () => {
    render(<MarketLeadersTab asOfTick={3} />);
    expect(useMarketLeaders).toHaveBeenCalledWith(true, 3, SELLERS_REGISTRY_LIMIT);
  });

  it("renders_all_seller_cards_in_backend_order", () => {
    render(<MarketLeadersTab asOfTick={3} />);

    const cards = screen.getAllByTestId("seller-registry-card");
    expect(cards).toHaveLength(3);
    expect(cards.map((card) => card.getAttribute("data-seller-id"))).toEqual(["3", "1", "7"]);
    expect(screen.getByText("Реестр селлеров")).toBeTruthy();
  });

  it("propagates_selected_seller_click", () => {
    const onHighlightSeller = vi.fn();
    render(<MarketLeadersTab asOfTick={3} highlightedSellerId={1} onHighlightSeller={onHighlightSeller} />);

    fireEvent.click(screen.getAllByTestId("seller-registry-card")[0]!);
    expect(onHighlightSeller).toHaveBeenCalledWith(3);
  });
});
