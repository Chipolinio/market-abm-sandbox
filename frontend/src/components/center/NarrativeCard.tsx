import type { WorkerState } from "@/api/types";
import type { ActiveShockDTO, MacroStateDTO } from "@/types/macro";
import type { ConnectionState } from "@/types/ticker";
import { buildMacroNarrative } from "@/utils/buildMacroNarrative";

export type NarrativeCardProps = {
  macro: MacroStateDTO | null;
  shocks: ActiveShockDTO[];
  workerState: WorkerState;
  connectionState: ConnectionState;
};

/** Zone C rule-based narrative above charts (Spec 014 §5.1). */
export function NarrativeCard({
  macro,
  shocks,
  workerState,
  connectionState,
}: NarrativeCardProps) {
  const { title, detail } = buildMacroNarrative(macro, shocks, {
    paused: workerState === "PAUSED",
  });
  const stale = connectionState !== "open";

  return (
    <section
      data-testid="narrative-card"
      className="shrink-0 border-b border-border pb-2"
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-foreground">{title}</p>
        {stale ? (
          <span data-testid="narrative-stale-indicator" className="shrink-0 text-[10px] text-amber-700">
            [Stale]
          </span>
        ) : null}
      </div>
      <p className="mt-0.5 text-xs text-muted">{detail}</p>
    </section>
  );
}
