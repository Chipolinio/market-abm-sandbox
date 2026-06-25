import { ControlPanel } from "@/components/ControlPanel";
import type { SimulationAction } from "@/components/sidebar/SimulationControlStrip";
import type { DynamicsTabProps, TerminalTabId } from "@/components/center/types";
import { TerminalTabs } from "@/components/center/TerminalTabs";
import { CyberEventTerminal } from "@/components/cyberlog/CyberEventTerminal";
import { TopSellersDashboard } from "@/components/cyberlog/TopSellersDashboard";
import { TickerRibbon } from "@/components/header/TickerRibbon";
import type { WorkerState } from "@/api/types";
import type { CyberLogLine } from "@/state/cyberLog";
import type { TickerRibbonProps } from "@/types/ticker";
import type { SimulationShockRequest } from "@/types/shock";

const EMPTY_DYNAMICS: DynamicsTabProps = {
  priceChartData: [],
  gmvChartData: [],
  backfillLoading: false,
  backfillError: null,
};

export type TradingTerminalLayoutProps = TickerRibbonProps & {
  onActionComplete?: (beforeState: WorkerState, action: SimulationAction) => Promise<void>;
  onShockQueued?: (body: SimulationShockRequest) => void;
  dynamics?: DynamicsTabProps;
  asOfTick?: number;
  cyberLogLines?: CyberLogLine[];
  activeTab?: TerminalTabId;
  onTabChange?: (tab: TerminalTabId) => void;
  pollAnalytics?: boolean;
  pollMatrixLive?: boolean;
  highlightedSellerId?: number | null;
  onHighlightSeller?: (sellerId: number | null) => void;
};

export function TradingTerminalLayout({
  metrics,
  connectionState,
  workerState,
  priceIndexDelta,
  flashCrashActive,
  onActionComplete,
  onShockQueued,
  dynamics = EMPTY_DYNAMICS,
  asOfTick = 0,
  cyberLogLines = [],
  activeTab,
  onTabChange,
  pollAnalytics = false,
  pollMatrixLive = false,
  highlightedSellerId = null,
  onHighlightSeller,
}: TradingTerminalLayoutProps) {
  const handleActionComplete =
    onActionComplete ?? (async (_beforeState: WorkerState, _action: SimulationAction) => undefined);
  const handleHighlightSeller = onHighlightSeller ?? (() => undefined);

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-white text-foreground">
      <header
        data-testid="zone-top-bar"
        className="flex h-14 w-full shrink-0 items-center border-b border-border bg-white px-4"
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
          className="flex h-full w-80 shrink-0 flex-col overflow-y-auto border-r border-border bg-white p-4"
        >
          <ControlPanel
            workerState={workerState}
            onActionComplete={handleActionComplete}
            onShockQueued={onShockQueued}
          />
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
            pollMatrixLive={pollMatrixLive}
            highlightedSellerId={highlightedSellerId}
            onHighlightSeller={handleHighlightSeller}
          />
        </main>

        <aside
          data-testid="zone-cyberlog"
          className="flex h-full w-96 shrink-0 flex-col overflow-hidden border-l border-border bg-white"
        >
          <TopSellersDashboard
            asOfTick={asOfTick}
            pollLive={pollAnalytics}
            highlightedSellerId={highlightedSellerId}
            onHighlightSeller={handleHighlightSeller}
          />
          <CyberEventTerminal lines={cyberLogLines} />
        </aside>
      </div>
    </div>
  );
}
