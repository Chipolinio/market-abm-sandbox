import type { SystemEventDTO } from "@/types/events";

export const CYBER_LOG_MAX_LINES = 200;

export type CyberLogLine = {
  event_id: string;
  tick_id: number;
  display_code: string;
  message: string;
  severity: SystemEventDTO["severity"];
};

function payloadString(payload: Record<string, unknown>, key: string): string | null {
  const value = payload[key];
  return value === undefined || value === null ? null : String(value);
}

/** Fallback message when backend `message` is empty (Spec 009 §5.3). */
export function resolveEventMessage(event: SystemEventDTO): string {
  if (event.message.trim().length > 0) {
    return event.message;
  }

  const payload = event.payload ?? {};

  switch (event.display_code) {
    case "DEMAND_SHOCK": {
      const pct = payloadString(payload, "pct") ?? payloadString(payload, "budget_cut_pct") ?? "?";
      return `Buyer budgets cut by ${pct}%`;
    }
    case "PRICING_WAR": {
      const sellerA = payloadString(payload, "seller_a") ?? payloadString(payload, "seller_a_id") ?? "?";
      const sellerB = payloadString(payload, "seller_b") ?? payloadString(payload, "seller_b_id") ?? "?";
      return `Seller_${sellerA} and Seller_${sellerB} entered a dumping loop`;
    }
    case "BANKRUPTCY": {
      const sellerId = payloadString(payload, "seller_id") ?? "?";
      return `Seller_${sellerId} depleted working capital and exited the market`;
    }
    case "FLASH_CRASH": {
      const pct = payloadString(payload, "pct") ?? payloadString(payload, "drop_pct") ?? "?";
      const window = payloadString(payload, "window") ?? payloadString(payload, "window_ticks") ?? "?";
      return `Market median price dropped ${pct}% over ${window} ticks`;
    }
    default:
      return event.display_code;
  }
}

export function toCyberLogLine(event: SystemEventDTO): CyberLogLine {
  return {
    event_id: event.event_id,
    tick_id: event.tick_id,
    display_code: event.display_code,
    message: resolveEventMessage(event),
    severity: event.severity,
  };
}

/** Prepend-only ring buffer; mutates `seenIds` for O(1) dedupe. */
export function prependEvents(
  existing: CyberLogLine[],
  incoming: SystemEventDTO[],
  maxLines: number,
  seenIds: Set<string>,
): CyberLogLine[] {
  let next = existing;

  for (const event of incoming) {
    if (seenIds.has(event.event_id)) {
      continue;
    }
    seenIds.add(event.event_id);
    next = [toCyberLogLine(event), ...next];
  }

  return next.slice(0, maxLines);
}

export function formatCyberLine(line: Pick<CyberLogLine, "tick_id" | "display_code" | "message">): string {
  return `[Тик ${line.tick_id}] ${line.display_code}: ${line.message}`;
}

/** Collapse 4+ BANKRUPTCY lines for the same tick into one macro event (Zone D spec). */
export function collapseCyberLogLines(lines: CyberLogLine[]): CyberLogLine[] {
  const bankruptcyCount = new Map<number, number>();
  for (const line of lines) {
    if (line.display_code === "BANKRUPTCY") {
      bankruptcyCount.set(line.tick_id, (bankruptcyCount.get(line.tick_id) ?? 0) + 1);
    }
  }

  const collapsedTicks = new Set(
    [...bankruptcyCount.entries()].filter(([, count]) => count > 3).map(([tickId]) => tickId),
  );
  const emittedCollapsed = new Set<number>();
  const result: CyberLogLine[] = [];

  for (const line of lines) {
    if (line.display_code === "BANKRUPTCY" && collapsedTicks.has(line.tick_id)) {
      if (emittedCollapsed.has(line.tick_id)) {
        continue;
      }
      emittedCollapsed.add(line.tick_id);
      const count = bankruptcyCount.get(line.tick_id) ?? 0;
      result.push({
        event_id: `collapsed-bankruptcy-${line.tick_id}`,
        tick_id: line.tick_id,
        display_code: "BANKRUPTCY",
        message: `Массовое выбывание алгоритмов (${count} игроков)`,
        severity: line.severity,
      });
      continue;
    }
    result.push(line);
  }

  return result;
}

export function severityClass(line: Pick<CyberLogLine, "severity" | "display_code">): string {
  if (line.severity === "critical" || line.display_code === "FLASH_CRASH") {
    return "text-red-400";
  }
  if (line.severity === "warning" || line.display_code === "PRICING_WAR") {
    return "text-amber-400";
  }
  return "text-green-400";
}
