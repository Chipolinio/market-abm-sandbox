// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCyberLog } from "@/hooks/useCyberLog";
import type { SystemEventDTO } from "@/types/events";

const fetchSystemEvents = vi.fn();

vi.mock("@/api/analytics", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/analytics")>();
  return {
    ...actual,
    fetchSystemEvents: (...args: unknown[]) => fetchSystemEvents(...args),
  };
});

function makeEvent(eventId: string, tickId: number): SystemEventDTO {
  return {
    event_id: eventId,
    tick_id: tickId,
    event_type: "demand_shock",
    display_code: "DEMAND_SHOCK",
    severity: "info",
    message: `Event at tick ${tickId}`,
  };
}

describe("useCyberLog", () => {
  beforeEach(() => {
    fetchSystemEvents.mockResolvedValue({
      events: [makeEvent("backfill-1", 1)],
    });
  });

  afterEach(() => {
    fetchSystemEvents.mockReset();
  });

  it("backfills_on_mount", async () => {
    const { result } = renderHook(() => useCyberLog(undefined, 0));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(fetchSystemEvents).toHaveBeenCalledWith(200);
    expect(result.current.lines).toHaveLength(1);
    expect(result.current.lines[0]?.event_id).toBe("backfill-1");
  });

  it("prepends_ws_events", async () => {
    const wsBatch = [makeEvent("ws-1", 10)];

    const { result, rerender } = renderHook(
      ({ events }: { events: SystemEventDTO[] | undefined }) => useCyberLog(events, 0),
      { initialProps: { events: undefined as SystemEventDTO[] | undefined } },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    rerender({ events: wsBatch });

    await waitFor(() => {
      expect(result.current.lines.some((line) => line.event_id === "ws-1")).toBe(true);
    });
    expect(result.current.lines[0]?.event_id).toBe("ws-1");
  });

  it("dedupes_ws_events_against_backfill", async () => {
    fetchSystemEvents.mockResolvedValue({
      events: [makeEvent("shared-1", 5)],
    });

    const { result, rerender } = renderHook(
      ({ events }: { events: SystemEventDTO[] | undefined }) => useCyberLog(events, 0),
      { initialProps: { events: undefined as SystemEventDTO[] | undefined } },
    );

    await waitFor(() => {
      expect(result.current.lines).toHaveLength(1);
    });

    rerender({ events: [makeEvent("shared-1", 5)] });

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.lines).toHaveLength(1);
  });

  it("backfills_again_on_reconnect_key_change", async () => {
    fetchSystemEvents
      .mockResolvedValueOnce({ events: [makeEvent("backfill-a", 1)] })
      .mockResolvedValueOnce({ events: [makeEvent("backfill-b", 2)] });

    const { result, rerender } = renderHook(
      ({ reconnectKey }: { reconnectKey: number }) => useCyberLog(undefined, reconnectKey),
      { initialProps: { reconnectKey: 0 } },
    );

    await waitFor(() => {
      expect(result.current.lines.some((line) => line.event_id === "backfill-a")).toBe(true);
    });

    rerender({ reconnectKey: 1 });

    await waitFor(() => {
      expect(fetchSystemEvents).toHaveBeenCalledTimes(2);
      expect(result.current.lines.some((line) => line.event_id === "backfill-b")).toBe(true);
    });
  });

  it("backfills_again_on_backfill_key_change", async () => {
    fetchSystemEvents
      .mockResolvedValueOnce({ events: [makeEvent("backfill-x", 3)] })
      .mockResolvedValueOnce({ events: [makeEvent("backfill-y", 4)] });

    const { result, rerender } = renderHook(
      ({ backfillKey }: { backfillKey: number }) => useCyberLog(undefined, 0, backfillKey),
      { initialProps: { backfillKey: 0 } },
    );

    await waitFor(() => {
      expect(result.current.lines.some((line) => line.event_id === "backfill-x")).toBe(true);
    });

    rerender({ backfillKey: 1 });

    await waitFor(() => {
      expect(fetchSystemEvents).toHaveBeenCalledTimes(2);
      expect(result.current.lines.some((line) => line.event_id === "backfill-y")).toBe(true);
    });
  });
});
