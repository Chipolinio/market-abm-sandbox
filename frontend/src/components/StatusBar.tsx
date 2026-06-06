import type { SimulationStatus, WorkerState } from "@/api/types";
/** @deprecated Spec 007 flat layout — replaced by TickerRibbon (Spec 009). */
import { ConnectionBadge } from "@/components/ConnectionBadge";
import type { ConnectionState } from "@/hooks/useTickStream";

type Props = {
  status: SimulationStatus | null;
  wsState: WorkerState | null;
  connectionState: ConnectionState;
  reconnectAttempt: number;
};

function formatTick(tick: number): string {
  if (tick >= 1_000_000) {
    return `${(tick / 1_000_000).toFixed(2)}M`;
  }
  if (tick >= 10_000) {
    return `${(tick / 1_000).toFixed(1)}k`;
  }
  return String(tick);
}

export function StatusBar({ status, wsState, connectionState, reconnectAttempt }: Props) {
  const state = status?.state ?? wsState ?? "IDLE";
  const tick = status?.current_tick ?? 0;
  const elapsed = status?.elapsed_time_seconds ?? 0;

  return (
    <header className="status-bar">
      <h1>Market ABM Dashboard</h1>
      <div className="status-bar-meta">
        <ConnectionBadge state={connectionState} reconnectAttempt={reconnectAttempt} />
        <span className="status-pill">{state}</span>
        <span>t={formatTick(tick)}</span>
        <span>{elapsed.toFixed(1)}s</span>
      </div>
    </header>
  );
}
