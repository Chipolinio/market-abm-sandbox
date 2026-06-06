import type { SimulationStatus, TickStreamPayload } from "@/api/types";

/**
 * Authoritative simulation tick for analytics (next tick to execute).
 * Prefer REST status over WS when WS still reports 0 after reconnect.
 */
export function resolveSimulationTick(
  status: SimulationStatus | null,
  lastPayload: TickStreamPayload | null,
): number {
  const fromStatus = status?.current_tick ?? 0;
  const fromWs = Math.max(
    lastPayload?.ticker_metrics?.current_tick ?? 0,
    lastPayload?.tick_id ?? 0,
  );
  return Math.max(fromStatus, fromWs);
}
