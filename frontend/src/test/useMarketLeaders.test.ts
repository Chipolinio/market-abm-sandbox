// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
});
