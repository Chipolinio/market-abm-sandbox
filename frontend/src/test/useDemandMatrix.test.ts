// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDemandMatrix } from "@/hooks/useDemandMatrix";

const fetchDemandMatrix = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchDemandMatrix: (...args: unknown[]) => fetchDemandMatrix(...args),
  };
});

function mockResponse(tickId: number) {
  return {
    run_id: "run-1",
    tick_id: tickId,
    grid_size: 3,
    row_count: 3,
    col_count: 3,
    x_labels: ["MaxProfit", "MaxVolume", "RatingMaximizer"],
    y_labels: ["rich", "standard", "low"],
    axis_x: "strategy_type",
    axis_y: "pvd_segment",
    cells: [{ row: 0, col: 0, density: 0.5 }],
  };
}

describe("useDemandMatrix", () => {
  beforeEach(() => {
    fetchDemandMatrix.mockImplementation(async (tickId: number) => mockResponse(tickId));
  });

  afterEach(() => {
    fetchDemandMatrix.mockReset();
  });

  it("does_not_fetch_when_disabled", async () => {
    renderHook(() => useDemandMatrix(false, 5));

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchDemandMatrix).not.toHaveBeenCalled();
  });

  it("fetches_once_when_enabled", async () => {
    const { result } = renderHook(() => useDemandMatrix(true, 5));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
    expect(fetchDemandMatrix).toHaveBeenCalledWith(5);
    expect(result.current.cells).toHaveLength(1);
    expect(result.current.colCount).toBe(3);
    expect(result.current.xLabels).toContain("MaxProfit");
  });

  it("refetches_on_re_enable_with_latest_tick_id", async () => {
    const { rerender } = renderHook(
      ({ enabled, tickId }: { enabled: boolean; tickId: number }) =>
        useDemandMatrix(enabled, tickId),
      { initialProps: { enabled: true, tickId: 5 } },
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledWith(5);
    });

    rerender({ enabled: false, tickId: 12 });
    rerender({ enabled: true, tickId: 12 });

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(2);
    });
    expect(fetchDemandMatrix).toHaveBeenLastCalledWith(12);
  });

  it("does_not_refetch_when_tick_id_changes_while_enabled", async () => {
    const { rerender } = renderHook(
      ({ enabled, tickId }: { enabled: boolean; tickId: number }) =>
        useDemandMatrix(enabled, tickId),
      { initialProps: { enabled: true, tickId: 5 } },
    );

    await waitFor(() => {
      expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
    });

    rerender({ enabled: true, tickId: 99 });

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);
  });

  it("polls_while_live_and_enabled", async () => {
    vi.useFakeTimers();
    renderHook(() => useDemandMatrix(true, 5, true));

    await act(async () => {
      await Promise.resolve();
    });
    expect(fetchDemandMatrix).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(fetchDemandMatrix).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
