import { TickerRibbon } from "@/components/header/TickerRibbon";
import type { TickerRibbonProps } from "@/types/ticker";

export type TradingTerminalLayoutProps = TickerRibbonProps;

export function TradingTerminalLayout({
  metrics,
  connectionState,
  workerState,
}: TradingTerminalLayoutProps) {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-slate-950 text-slate-100">
      <aside
        data-testid="zone-left-sidebar"
        className="flex w-80 shrink-0 flex-col overflow-hidden border-r border-slate-800 bg-slate-900"
      />

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
