import { TickerRibbon } from "@/components/header/TickerRibbon";
import { EnvironmentConfigurator } from "@/components/sidebar/EnvironmentConfigurator";
import { ShocksControlPanel } from "@/components/sidebar/ShocksControlPanel";
import { SimulationControlStrip } from "@/components/sidebar/SimulationControlStrip";
import type { WorkerState } from "@/api/types";
import type { TickerRibbonProps } from "@/types/ticker";

export type TradingTerminalLayoutProps = TickerRibbonProps & {
  onActionComplete?: (beforeState: WorkerState) => Promise<void>;
};

function isConfigurableState(state: WorkerState): boolean {
  return state === "IDLE" || state === "STOPPED";
}

export function TradingTerminalLayout({
  metrics,
  connectionState,
  workerState,
  onActionComplete,
}: TradingTerminalLayoutProps) {
  const handleActionComplete = onActionComplete ?? (async () => undefined);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      <aside
        data-testid="zone-left-sidebar"
        className="flex w-80 shrink-0 flex-col overflow-hidden border-r border-slate-800 bg-slate-900"
      >
        <section className="border-b border-slate-800 p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase text-slate-400">Environment</h2>
          <EnvironmentConfigurator disabled={!isConfigurableState(workerState)} />
        </section>
        <section className="border-b border-slate-800 p-4">
          <h2 className="mb-3 text-xs font-semibold uppercase text-slate-400">Macro Shocks</h2>
          <ShocksControlPanel />
        </section>
        <section className="mt-auto p-4">
          <SimulationControlStrip state={workerState} onActionComplete={handleActionComplete} />
        </section>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center border-b border-slate-800 px-4">
          <TickerRibbon
            metrics={metrics}
            connectionState={connectionState}
            workerState={workerState}
          />
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto bg-slate-950 p-4" data-testid="zone-main" />
      </div>

      <aside
        data-testid="zone-cyberlog"
        className="flex w-96 shrink-0 flex-col border-l border-slate-800 bg-slate-900"
      />
    </div>
  );
}
