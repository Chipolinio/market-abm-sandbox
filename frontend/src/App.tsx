import { useCallback, useEffect, useMemo, useState } from "react";

import type { TerminalTabId } from "@/components/center/types";
import type { TickStreamPayload } from "@/api/types";
import { useCyberLog } from "@/hooks/useCyberLog";
import { useDashboardSeries } from "@/hooks/useDashboardSeries";
import { useFlashCrashAlarm } from "@/hooks/useFlashCrashAlarm";
import { usePriceIndexDelta } from "@/hooks/usePriceIndexDelta";
import { useSimulationStatus } from "@/hooks/useSimulationStatus";
import { useTickStream } from "@/hooks/useTickStream";
import { TradingTerminalLayout } from "@/layouts/TradingTerminalLayout";
import type { WorkerState } from "@/api/types";

export default function App() {
  const [activeTab, setActiveTab] = useState<TerminalTabId>("dynamics");
  const { status, refresh } = useSimulationStatus();
  const {
    priceChartData,
    gmvChartData,
    backfillLoading,
    backfillError,
    handlePayload,
    reloadBackfill,
  } = useDashboardSeries();

  const handleDynamicsPayload = useCallback(
    (payload: TickStreamPayload) => {
      if (activeTab === "dynamics") {
        handlePayload(payload);
      }
    },
    [activeTab, handlePayload],
  );

  useEffect(() => {
    if (activeTab === "dynamics") {
      void reloadBackfill();
    }
  }, [activeTab, reloadBackfill]);

  const { connectionState, lastPayload } = useTickStream({
    onPayload: handleDynamicsPayload,
  });

  const { lines: cyberLogLines } = useCyberLog(lastPayload?.events);

  const priceIndexDelta = usePriceIndexDelta(lastPayload?.ticker_metrics?.market_price_index);
  const flashCrashActive = useFlashCrashAlarm(lastPayload?.events);

  const workerState: WorkerState = status?.state ?? lastPayload?.worker_state ?? "IDLE";
  const asOfTick =
    lastPayload?.tick_id ??
    lastPayload?.ticker_metrics?.current_tick ??
    status?.current_tick ??
    0;
  const showFailed =
    workerState === "FAILED" || (status?.last_error !== null && status?.last_error !== undefined);

  const dynamics = useMemo(
    () => ({
      priceChartData,
      gmvChartData,
      backfillLoading,
      backfillError,
    }),
    [priceChartData, gmvChartData, backfillLoading, backfillError],
  );

  const onActionComplete = useCallback(
    async (beforeState: WorkerState) => {
      for (let i = 0; i < 25; i += 1) {
        const next = await refresh();
        if (next !== null && next.state !== beforeState) {
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 50));
      }
      void reloadBackfill();
    },
    [refresh, reloadBackfill],
  );

  return (
    <>
      {showFailed ? (
        <div
          className="fixed left-0 right-0 top-0 z-50 bg-red-950 px-4 py-2 text-center text-sm text-red-200"
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
        dynamics={dynamics}
      />
    </>
  );
}
