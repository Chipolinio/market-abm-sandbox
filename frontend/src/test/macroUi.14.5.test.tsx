// Spec 014 §13.5 — CategoryRankingTab (slice 14.5).
// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CategoryRankingTab } from "@/components/center/CategoryRankingTab";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("14.5 CategoryRankingTab", () => {
  it("renders_category_rows", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          run_id: "r1",
          tick_id: 3,
          rows: [
            {
              category_id: 0,
              n_listings: 2,
              median_score: 1.234,
              median_price: 110.0,
              sales_window_sum: 6.0,
              top_listing_ids: [10, 11],
            },
            {
              category_id: 1,
              n_listings: 3,
              median_score: 0.9,
              median_price: 60.0,
              sales_window_sum: 12.0,
              top_listing_ids: [20, 21, 22],
            },
          ],
        }),
      })),
    );

    render(<CategoryRankingTab asOfTick={3} />);
    await waitFor(() => {
      expect(screen.getByTestId("category-row-0")).toBeTruthy();
    });
    expect(screen.getByTestId("category-row-1")).toBeTruthy();
    expect(screen.getByTestId("category-ranking-panel").textContent).toContain("1.234");
    expect(screen.getByTestId("category-row-0").textContent).toContain("10, 11");
  });
});
