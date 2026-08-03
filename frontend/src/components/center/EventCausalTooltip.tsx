import type { DemandShockCausal } from "@/utils/demandShockCausal";

export type EventCausalTooltipProps = {
  causal: DemandShockCausal | null;
  onClose: () => void;
};

/** Popup for crash marker — impulse / stress_after / half-life from payload (Spec 014 §5.3). */
export function EventCausalTooltip({ causal, onClose }: EventCausalTooltipProps) {
  if (causal === null) {
    return null;
  }

  return (
    <div
      data-testid="event-causal-tooltip"
      role="dialog"
      aria-label="Demand shock causal"
      className="absolute right-2 top-2 z-10 min-w-[12rem] rounded border border-border bg-white p-3 text-xs shadow-md"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="font-semibold text-foreground">Demand shock</span>
        <button
          type="button"
          className="text-[10px] text-muted hover:text-foreground"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <dl className="space-y-1 text-muted-strong">
        <div className="flex justify-between gap-4">
          <dt>Impulse</dt>
          <dd className="font-mono text-foreground">{causal.impulse.toFixed(2)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Stress after</dt>
          <dd className="font-mono text-foreground">{causal.stress_after.toFixed(2)}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt>Est. half-life</dt>
          <dd className="font-mono text-foreground">{causal.est_half_life_ticks.toFixed(0)} ticks</dd>
        </div>
        {causal.scenario !== undefined ? (
          <div className="flex justify-between gap-4">
            <dt>Scenario</dt>
            <dd className="text-foreground">{causal.scenario}</dd>
          </div>
        ) : null}
      </dl>
    </div>
  );
}
