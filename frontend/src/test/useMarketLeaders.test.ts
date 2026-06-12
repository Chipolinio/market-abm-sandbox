// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SELLERS_REGISTRY_LIMIT } from "@/api/analytics";
import { useMarketLeaders } from "@/hooks/useMarketLeaders";

const fetchMarketLeaders = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchMarketLeaders: (...args: unknown[]) => fetchMarketLeaders(...args),
  };
});

describe("useMarketLeaders", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchMarketLeaders.mockResolvedValue({
      run_id: "run-1",
      tick_id: 3,
      leaders: [],
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    fetchMarketLeaders.mockReset();
  });

  it("polls_only_when_active", async () => {
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useMarketLeaders(enabled, 3),
      { initialProps: { enabled: false } },
    );

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(fetchMarketLeaders).not.toHaveBeenCalled();

    rerender({ enabled: true });
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchMarketLeaders).toHaveBeenCalledTimes(1);
    expect(fetchMarketLeaders).toHaveBeenCalledWith(3, 5);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    expect(fetchMarketLeaders).toHaveBeenCalledTimes(2);

    rerender({ enabled: false });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(fetchMarketLeaders).toHaveBeenCalledTimes(2);
  });

  it("fetches_full_registry_when_custom_limit_passed", async () => {
    fetchMarketLeaders.mockResolvedValue({
      run_id: "run-1",
      tick_id: 5,
      leaders: [
        {
          seller_id: 1,
          working_capital: 100,
          tick_revenue: 10,
          cumulative_revenue: 50,
          is_bankrupt: false,
          algorithm_type: "CB",
          inventory_stock: 2,
          logic_status: "roi_optimization",
        },
      ],
    });

    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useMarketLeaders(enabled, 5, SELLERS_REGISTRY_LIMIT),
      { initialProps: { enabled: false } },
    );

    rerender({ enabled: true });
    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchMarketLeaders).toHaveBeenCalledWith(5, SELLERS_REGISTRY_LIMIT);
  });

  it("no_poll_after_tab_becomes_inactive", async () => {
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => useMarketLeaders(enabled, 5),
      { initialProps: { enabled: true } },
    );

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchMarketLeaders).toHaveBeenCalledTimes(1);

    rerender({ enabled: false });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(20_000);
    });
    expect(fetchMarketLeaders).toHaveBeenCalledTimes(1);
  });
});
