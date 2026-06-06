import { describe, expect, it } from "vitest";

import {
  CYBER_LOG_MAX_LINES,
  formatCyberLine,
  prependEvents,
} from "@/state/cyberLog";
import type { CyberLogLine } from "@/state/cyberLog";
import type { SystemEventDTO } from "@/types/events";

function makeEvent(
  eventId: string,
  overrides: Partial<SystemEventDTO> = {},
): SystemEventDTO {
  return {
    event_id: eventId,
    tick_id: 1,
    event_type: "DEMAND_SHOCK",
    display_code: "DEMAND_SHOCK",
    severity: "warning",
    message: `Event ${eventId}`,
    ...overrides,
  };
}

describe("prependEvents", () => {
  it("dedupes_event_id", () => {
    const seenIds = new Set<string>();
    const incoming = [makeEvent("evt-1"), makeEvent("evt-1")];

    const result = prependEvents([], incoming, CYBER_LOG_MAX_LINES, seenIds);

    expect(result).toHaveLength(1);
    expect(seenIds.has("evt-1")).toBe(true);
  });

  it("respects_max_200", () => {
    const seenIds = new Set<string>();
    const existing: CyberLogLine[] = Array.from({ length: 199 }, (_, index) => ({
      event_id: `old-${index}`,
      tick_id: index,
      display_code: "DEMAND_SHOCK",
      message: `old-${index}`,
      severity: "info",
    }));
    const incoming = [makeEvent("evt-new-1"), makeEvent("evt-new-2"), makeEvent("evt-new-3")];

    const result = prependEvents(existing, incoming, CYBER_LOG_MAX_LINES, seenIds);

    expect(result).toHaveLength(200);
    expect(result[0]?.event_id).toBe("evt-new-3");
    expect(result[1]?.event_id).toBe("evt-new-2");
    expect(result[2]?.event_id).toBe("evt-new-1");
  });
});

describe("formatCyberLine", () => {
  it("formats_tick_prefix", () => {
    const line: CyberLogLine = {
      event_id: "evt-42",
      tick_id: 42,
      display_code: "DEMAND_SHOCK",
      message: "Buyer budgets cut by 30%",
      severity: "warning",
    };

    expect(formatCyberLine(line)).toBe(
      "[Tick 42] DEMAND_SHOCK: Buyer budgets cut by 30%",
    );
  });
});
