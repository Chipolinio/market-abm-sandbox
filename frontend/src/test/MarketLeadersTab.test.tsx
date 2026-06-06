// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketLeadersTab } from "@/components/center/MarketLeadersTab";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const useMarketLeaders = vi.fn();

vi.mock("@/hooks/useMarketLeaders", () => ({
  useMarketLeaders: () => useMarketLeaders(),
}));

const mockLeaders: MarketLeaderRowDTO[] = [
  {
    seller_id: 3,
    working_capital: 9_500.5,
    tick_revenue: 120.25,
    cumulative_revenue: 4_200.0,
    is_bankrupt: false,
  },
  {
    seller_id: 1,
    working_capital: 7_100.0,
    tick_revenue: 80.0,
    cumulative_revenue: 3_100.5,
    is_bankrupt: false,
  },
  {
    seller_id: 7,
    working_capital: 5_000.0,
    tick_revenue: 0.0,
    cumulative_revenue: 1_800.0,
    is_bankrupt: true,
  },
  {
    seller_id: 2,
    working_capital: 3_200.75,
    tick_revenue: 45.5,
    cumulative_revenue: 900.0,
    is_bankrupt: false,
  },
  {
    seller_id: 9,
    working_capital: 1_500.0,
    tick_revenue: 10.0,
    cumulative_revenue: 400.0,
    is_bankrupt: false,
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
  it("renders_top5_rows", () => {
    const { container } = render(<MarketLeadersTab />);

    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(5);
  });

  it("preserves_backend_order_without_client_sort", () => {
    render(<MarketLeadersTab />);

    const sellerCells = screen.getAllByTestId("leader-seller-id");
    expect(sellerCells.map((cell) => cell.textContent)).toEqual(["3", "1", "7", "2", "9"]);
  });
});
