import { describe, expect, it } from "vitest";

import {
  CYBER_LOG_MAX_LINES,
  collapseCyberLogLines,
  formatCyberLine,
  prependEvents,
  resolveEventMessage,
  severityClass,
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
      "[Тик 42] DEMAND_SHOCK: Buyer budgets cut by 30%",
    );
  });
});

describe("collapseCyberLogLines", () => {
  it("collapses_four_or_more_bankruptcies_on_same_tick", () => {
    const lines: CyberLogLine[] = [
      { event_id: "b4", tick_id: 10, display_code: "BANKRUPTCY", message: "s4", severity: "info" },
      { event_id: "b3", tick_id: 10, display_code: "BANKRUPTCY", message: "s3", severity: "info" },
      { event_id: "b2", tick_id: 10, display_code: "BANKRUPTCY", message: "s2", severity: "info" },
      { event_id: "b1", tick_id: 10, display_code: "BANKRUPTCY", message: "s1", severity: "info" },
    ];

    const collapsed = collapseCyberLogLines(lines);
    expect(collapsed).toHaveLength(1);
    expect(collapsed[0]?.message).toContain("Массовое выбывание алгоритмов (4 игроков)");
  });

  it("keeps_three_or_fewer_bankruptcies_separate", () => {
    const lines: CyberLogLine[] = [
      { event_id: "b3", tick_id: 10, display_code: "BANKRUPTCY", message: "s3", severity: "info" },
      { event_id: "b2", tick_id: 10, display_code: "BANKRUPTCY", message: "s2", severity: "info" },
      { event_id: "b1", tick_id: 10, display_code: "BANKRUPTCY", message: "s1", severity: "info" },
    ];

    expect(collapseCyberLogLines(lines)).toHaveLength(3);
  });
});

describe("resolveEventMessage", () => {
  it("prefers_backend_message", () => {
    expect(
      resolveEventMessage(
        makeEvent("evt-1", { message: "Backend ready message", display_code: "DEMAND_SHOCK" }),
      ),
    ).toBe("Backend ready message");
  });

  it("falls_back_for_empty_message", () => {
    expect(
      resolveEventMessage(
        makeEvent("evt-1", {
          message: "   ",
          display_code: "BANKRUPTCY",
          payload: { seller_id: 3 },
        }),
      ),
    ).toBe("Seller_3 depleted working capital and exited the market");
  });
});

describe("severityClass", () => {
  it("maps_flash_crash_to_red", () => {
    expect(
      severityClass({
        severity: "info",
        display_code: "FLASH_CRASH",
      }),
    ).toBe("text-red-400");
  });

  it("maps_pricing_war_to_amber", () => {
    expect(
      severityClass({
        severity: "info",
        display_code: "PRICING_WAR",
      }),
    ).toBe("text-amber-400");
  });

  it("maps_info_to_green", () => {
    expect(
      severityClass({
        severity: "info",
        display_code: "DEMAND_SHOCK",
      }),
    ).toBe("text-green-400");
  });
});
