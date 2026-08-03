import type { ConnectionState } from "@/types/ticker";
import type { MacroStateDTO } from "@/types/macro";

export type MacroStatePanelProps = {
  macro: MacroStateDTO | null;
  connectionState?: ConnectionState;
};

function barPct(value: number, cap: number): number {
  if (cap <= 0) {
    return 0;
  }
  const pct = (value / cap) * 100;
  if (pct < 0) {
    return 0;
  }
  if (pct > 100) {
    return 100;
  }
  return pct;
}

function staleLabel(connectionState: ConnectionState | undefined): string | null {
  if (connectionState === undefined || connectionState === "open") {
    return null;
  }
  if (connectionState === "connecting") {
    return "[Stale]";
  }
  if (connectionState === "error") {
    return "[Disconnected]";
  }
  return "[Disconnected]";
}

/** Zone A stress/expansion bars + episode + ETA (Spec 014 §4.3). */
export function MacroStatePanel({
  macro,
  connectionState = "open",
}: MacroStatePanelProps) {
  const stale = staleLabel(connectionState);

  if (macro === null) {
    return (
      <section data-testid="macro-state-panel" className="mb-4 rounded border border-border p-3">
        <h2 className="mb-2 text-xs uppercase tracking-wider text-muted">Macro</h2>
        <p className="text-xs text-muted">Нет данных macro_state</p>
      </section>
    );
  }

  const stressWidth = barPct(macro.stress, macro.stress_cap);
  const expansionWidth = barPct(macro.expansion, macro.expansion_cap);
  const eta =
    macro.est_recovery_eta_ticks === null ? "—" : `~${macro.est_recovery_eta_ticks} ticks`;

  return (
    <section data-testid="macro-state-panel" className="mb-4 rounded border border-border p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="text-xs uppercase tracking-wider text-muted">Macro</h2>
        {stale !== null ? (
          <span data-testid="macro-stale-indicator" className="text-[10px] text-amber-700">
            {stale}
          </span>
        ) : null}
      </div>

      <div className="mb-2 space-y-1.5">
        <div className="flex items-center justify-between text-[11px] text-muted-strong">
          <span>Stress</span>
          <span>
            {macro.stress.toFixed(2)} / {macro.stress_cap}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-slate-100">
          <div
            data-testid="macro-stress-bar"
            className="h-full bg-red-600"
            style={{ width: `${stressWidth}%` }}
          />
        </div>

        <div className="flex items-center justify-between text-[11px] text-muted-strong">
          <span>Expansion</span>
          <span>
            {macro.expansion.toFixed(2)} / {macro.expansion_cap}
          </span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-slate-100">
          <div
            data-testid="macro-expansion-bar"
            className="h-full bg-emerald-600"
            style={{ width: `${expansionWidth}%` }}
          />
        </div>
      </div>

      <div className="flex justify-between text-[11px] text-foreground">
        <span>episode #{macro.episode_id}</span>
        <span>ETA Recovery {eta}</span>
      </div>
    </section>
  );
}
