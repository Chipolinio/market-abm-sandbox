import type { ActiveShockDTO } from "@/types/macro";
import type { ConnectionState } from "@/types/ticker";
import { formatActiveShockLine } from "@/utils/formatActiveShock";

export type ActiveShocksPanelProps = {
  shocks: ActiveShockDTO[];
  connectionState?: ConnectionState;
  maxRows?: number;
};

/** Zone A list of active shocks (Spec 014 §4.4). */
export function ActiveShocksPanel({
  shocks,
  connectionState = "open",
  maxRows = 8,
}: ActiveShocksPanelProps) {
  const stale = connectionState !== "open";
  const visible = shocks.slice(0, maxRows);
  const overflow = Math.max(0, shocks.length - visible.length);

  return (
    <section data-testid="active-shocks-panel" className="mb-4 rounded border border-border p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-xs uppercase tracking-wider text-muted">Active Shocks</h2>
        {stale ? (
          <span data-testid="shocks-stale-indicator" className="text-[10px] text-amber-700">
            [Stale]
          </span>
        ) : null}
      </div>

      {visible.length === 0 ? (
        <p className="text-xs text-muted">No active shocks</p>
      ) : (
        <ul className="space-y-1">
          {visible.map((shock, index) => (
            <li
              key={`${shock.shock_type}-${shock.applied_at_tick}-${index}`}
              className="font-mono text-[11px] text-foreground"
            >
              {formatActiveShockLine(shock)}
            </li>
          ))}
        </ul>
      )}
      {overflow > 0 ? (
        <p className="mt-1 text-[10px] text-muted">+{overflow} more</p>
      ) : null}
    </section>
  );
}
