import { useCallback, useEffect, useMemo, useState } from "react";

import type { TerminalTabId } from "@/components/center/types";
import { useCyberLog } from "@/hooks/useCyberLog";
import { useDashboardSeries } from "@/hooks/useDashboardSeries";
import { useFlashCrashAlarm } from "@/hooks/useFlashCrashAlarm";
import { usePriceIndexDelta } from "@/hooks/usePriceIndexDelta";
import { useSimulationStatus } from "@/hooks/useSimulationStatus";
import { useTickStream } from "@/hooks/useTickStream";
import type { SimulationAction } from "@/components/sidebar/SimulationControlStrip";
import { TradingTerminalLayout } from "@/layouts/TradingTerminalLayout";
import type { WorkerState } from "@/api/types";
import { toLastCompletedTick } from "@/utils/analyticsTick";
import { resolveSimulationTick } from "@/utils/simulationTick";

export default function App() {
  const [activeTab, setActiveTab] = useState<TerminalTabId>("dynamics");
  const [cyberLogBackfillKey, setCyberLogBackfillKey] = useState(0);
  const [highlightedSellerId, setHighlightedSellerId] = useState<number | null>(null);
  const { status, refresh } = useSimulationStatus();

  const { connectionState, lastPayload, reconnectAttempt } = useTickStream();

  const workerState: WorkerState = status?.state ?? lastPayload?.worker_state ?? "IDLE";
  const pollAnalytics = workerState === "RUNNING" || workerState === "PAUSED";
  const pollCyberLogLive = workerState === "RUNNING";

  const {
    priceChartData,
    gmvChartData,
    backfillLoading,
    backfillError,
    handlePayload,
    reloadBackfill,
    clearSeries,
  } = useDashboardSeries(pollAnalytics, reconnectAttempt);

  useEffect(() => {
    if (lastPayload !== null) {
      handlePayload(lastPayload);
    }
  }, [lastPayload, handlePayload]);

  useEffect(() => {
    if (activeTab === "dynamics") {
      void reloadBackfill();
    }
  }, [activeTab, reloadBackfill]);

  const nextTick = resolveSimulationTick(status, lastPayload);
  const asOfTick = toLastCompletedTick(nextTick);

  const { lines: cyberLogLines, reset: resetCyberLog } = useCyberLog(
    lastPayload?.events,
    reconnectAttempt,
    cyberLogBackfillKey,
    {
      pollWhileRunning: pollCyberLogLive,
    },
  );

  const priceIndexDelta = usePriceIndexDelta(lastPayload?.ticker_metrics?.market_price_index);
  const flashCrashActive = useFlashCrashAlarm(lastPayload?.events);

  const showFailed =
    workerState === "FAILED" || (status?.last_error !== null && status?.last_error !== undefined);

  const dynamics = useMemo(
    () => ({
      priceChartData,
      gmvChartData,
      backfillLoading,
      backfillError,
      highlightedSellerId,
    }),
    [priceChartData, gmvChartData, backfillLoading, backfillError, highlightedSellerId],
  );

  const onActionComplete = useCallback(
    async (beforeState: WorkerState, action: SimulationAction) => {
      for (let i = 0; i < 25; i += 1) {
        const next = await refresh();
        if (next !== null && next.state !== beforeState) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
      }

      if (action === "reset") {
        clearSeries();
        resetCyberLog();
        void reloadBackfill();
      }

      setCyberLogBackfillKey((key) => key + 1);
    },
    [refresh, reloadBackfill, clearSeries, resetCyberLog],
  );

  return (
    <>
      {showFailed ? (
        <div
          className="fixed left-0 right-0 top-0 z-50 border-b border-red-200 bg-red-50 px-4 py-2 text-center text-sm text-red-800"
          role="alert"
        >
          Simulation failed: {status?.last_error ?? "see worker logs"}
        </div>
      ) : null}

      <TradingTerminalLayout
        metrics={lastPayload?.ticker_metrics ?? null}
        connectionState={connectionState}
        workerState={workerState}
        priceIndexDelta={priceIndexDelta}
        flashCrashActive={flashCrashActive}
        onActionComplete={onActionComplete}
        cyberLogLines={cyberLogLines}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        asOfTick={asOfTick}
        pollAnalytics={pollAnalytics}
        pollMatrixLive={workerState === "RUNNING" && activeTab === "demand_matrix"}
        dynamics={dynamics}
        highlightedSellerId={highlightedSellerId}
        onHighlightSeller={setHighlightedSellerId}
      />
    </>
  );
}
