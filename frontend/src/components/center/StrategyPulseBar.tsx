import type { StrategyPulseResponse } from "@/types/observability";
import { strategyTypeLabel } from "@/utils/uiLabels";

export type StrategyPulseBarProps = {
  pulse: StrategyPulseResponse | null;
  loading?: boolean;
};

/** Three mini strategy DI cards + PANIC flag (Spec 014 §6.1). */
export function StrategyPulseBar({ pulse, loading = false }: StrategyPulseBarProps) {
  if (loading && pulse === null) {
    return (
      <div data-testid="strategy-pulse-bar" className="shrink-0 text-[10px] text-muted">
        Пульс стратегий…
      </div>
    );
  }
  if (pulse === null || pulse.strategies.length === 0) {
    return (
      <div data-testid="strategy-pulse-bar" className="shrink-0 text-[10px] text-muted">
        Нет данных пульса стратегий
      </div>
    );
  }

  return (
    <div data-testid="strategy-pulse-bar" className="shrink-0 border-b border-border pb-2">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-muted">Пульс стратегий</span>
        {pulse.panic_active ? (
          <span
            data-testid="strategy-panic-badge"
            className="rounded border border-red-300 bg-red-50 px-1.5 py-0.5 text-[10px] font-semibold text-red-700"
          >
            ПАНИКА
          </span>
        ) : null}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {pulse.strategies.map((row) => (
          <div
            key={row.strategy_type}
            data-testid={`strategy-pulse-${row.strategy_type}`}
            className="rounded border border-border px-2 py-1.5"
          >
            <div className="truncate text-[10px] text-muted">
              {strategyTypeLabel(row.strategy_type)}
            </div>
            <div className="font-mono text-xs text-foreground">
              ИС {row.avg_demand_index.toFixed(2)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
