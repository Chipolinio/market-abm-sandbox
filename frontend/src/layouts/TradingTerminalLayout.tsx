import { ControlPanel } from "@/components/ControlPanel";
import type { DynamicsTabProps, TerminalTabId } from "@/components/center/types";
import { TerminalTabs } from "@/components/center/TerminalTabs";
import { CyberEventTerminal } from "@/components/cyberlog/CyberEventTerminal";
import { TickerRibbon } from "@/components/header/TickerRibbon";
import type { WorkerState } from "@/api/types";
import type { CyberLogLine } from "@/state/cyberLog";
import type { TickerRibbonProps } from "@/types/ticker";

const EMPTY_DYNAMICS: DynamicsTabProps = {
  priceChartData: [],
  gmvChartData: [],
  backfillLoading: false,
  backfillError: null,
};

export type TradingTerminalLayoutProps = TickerRibbonProps & {
  onActionComplete?: (beforeState: WorkerState) => Promise<void>;
  dynamics?: DynamicsTabProps;
  asOfTick?: number;
  cyberLogLines?: CyberLogLine[];
  activeTab?: TerminalTabId;
  onTabChange?: (tab: TerminalTabId) => void;
};

export function TradingTerminalLayout({
  metrics,
  connectionState,
  workerState,
  priceIndexDelta,
  flashCrashActive,
  onActionComplete,
  dynamics = EMPTY_DYNAMICS,
  asOfTick = 0,
  cyberLogLines = [],
  activeTab,
  onTabChange,
}: TradingTerminalLayoutProps) {
  const handleActionComplete = onActionComplete ?? (async () => undefined);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-slate-50">
      <header
        data-testid="zone-top-bar"
        className="flex h-14 w-full shrink-0 items-center border-b border-slate-800 px-4"
      >
        <TickerRibbon
          metrics={metrics}
          connectionState={connectionState}
          workerState={workerState}
          priceIndexDelta={priceIndexDelta}
          flashCrashActive={flashCrashActive}
        />
      </header>

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <aside
          data-testid="zone-left-sidebar"
          className="flex h-full w-80 shrink-0 flex-col overflow-y-auto border-r border-slate-800 bg-slate-900 p-4"
        >
          <ControlPanel workerState={workerState} onActionComplete={handleActionComplete} />
        </aside>

        <main
          data-testid="zone-main"
          className="flex h-full min-w-0 flex-1 flex-col overflow-hidden p-4"
        >
          <TerminalTabs
            dynamics={dynamics}
            asOfTick={asOfTick}
            activeTab={activeTab}
            onTabChange={onTabChange}
          />
        </main>

        <aside
          data-testid="zone-cyberlog"
          className="flex h-full w-96 shrink-0 flex-col border-l border-slate-800 bg-slate-900"
        >
          <CyberEventTerminal lines={cyberLogLines} />
        </aside>
      </div>
    </div>
  );
}
