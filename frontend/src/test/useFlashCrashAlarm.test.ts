// @vitest-environment jsdom
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useFlashCrashAlarm } from "@/hooks/useFlashCrashAlarm";
import type { SystemEventDTO } from "@/types/events";

afterEach(() => {
  cleanup();
});

const flashCrashEvent: SystemEventDTO = {
  event_id: "run:10:flash:0",
  tick_id: 10,
  event_type: "flash_crash",
  display_code: "FLASH_CRASH",
  severity: "critical",
  message: "Market median price dropped 40% over 10 ticks",
};

describe("useFlashCrashAlarm", () => {
  it("active_when_critical_flash_crash_in_frame", () => {
    const { result, rerender } = renderHook(
      ({ events }: { events: SystemEventDTO[] | undefined }) => useFlashCrashAlarm(events),
      { initialProps: { events: undefined as SystemEventDTO[] | undefined } },
    );

    expect(result.current).toBe(false);

    rerender({ events: [flashCrashEvent] });
    expect(result.current).toBe(true);
  });

  it("inactive_for_non_critical_events", () => {
    const { result } = renderHook(() =>
      useFlashCrashAlarm([
        {
          ...flashCrashEvent,
          severity: "warning",
        },
      ]),
    );

    expect(result.current).toBe(false);
  });
});
