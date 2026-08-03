import { useCallback, useEffect, useMemo, useState } from "react";

import type { EventMarker, TerminalTabId } from "@/components/center/types";
import { useCyberLog } from "@/hooks/useCyberLog";
import { useDashboardSeries } from "@/hooks/useDashboardSeries";
import { useFlashCrashAlarm } from "@/hooks/useFlashCrashAlarm";
import { usePriceIndexDelta } from "@/hooks/usePriceIndexDelta";
import { useSimulationStatus } from "@/hooks/useSimulationStatus";
import { useTickStream } from "@/hooks/useTickStream";
import type { SimulationAction } from "@/components/sidebar/SimulationControlStrip";
import { TradingTerminalLayout } from "@/layouts/TradingTerminalLayout";
import { ResearchLab } from "@/pages/ResearchLab";
import type { WorkerState } from "@/api/types";
import type { ActiveShockDTO, MacroStateDTO } from "@/types/macro";
import type { ExperimentSummaryRow } from "@/types/experiments";
import { fetchExperimentSummary } from "@/api/experiments";
import { toLastCompletedTick } from "@/utils/analyticsTick";
import { markerLabelForShock, mergeEventMarker } from "@/utils/eventMarkers";
import { resolveSimulationTick } from "@/utils/simulationTick";
import type { SimulationShockRequest } from "@/types/shock";

function isResearchHash(): boolean {
  return typeof window !== "undefined" && window.location.hash.includes("research");
}

export default function App() {
  const [researchMode, setResearchMode] = useState(isResearchHash);
  const [researchRows, setResearchRows] = useState<ExperimentSummaryRow[]>([]);
  const researchId = "paper_grid_v1";
  const [activeTab, setActiveTab] = useState<TerminalTabId>("dynamics");
  const [cyberLogBackfillKey, setCyberLogBackfillKey] = useState(0);
  const [highlightedSellerId, setHighlightedSellerId] = useState<number | null>(null);
  const [crashMarkers, setCrashMarkers] = useState<EventMarker[]>([]);
  /** Spec 014 §4.1.1 — keep last known macro on WS disconnect (stale). */
  const [macroState, setMacroState] = useState<MacroStateDTO | null>(null);
  const [activeShocks, setActiveShocks] = useState<ActiveShockDTO[]>([]);
  const [refPrice, setRefPrice] = useState<number | null>(null);
  const { status, refresh } = useSimulationStatus();

  useEffect(() => {
    const onHash = () => setResearchMode(isResearchHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    if (!researchMode) {
      return;
    }
    let cancelled = false;
    void fetchExperimentSummary(researchId)
      .then((res) => {
        if (!cancelled) {
          setResearchRows(res.rows);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResearchRows([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [researchMode, researchId]);

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
      if (lastPayload.macro_state !== undefined) {
        setMacroState(lastPayload.macro_state);
      }
      if (lastPayload.active_shocks !== undefined) {
        setActiveShocks(lastPayload.active_shocks);
      }
      if (lastPayload.ref_price !== undefined) {
        setRefPrice(lastPayload.ref_price);
      }
      for (const event of lastPayload.events ?? []) {
        if (event.display_code !== "DEMAND_SHOCK") {
          continue;
        }
        const isBoom =
          (event.payload as Record<string, unknown> | null | undefined)
            ?.shock_type === "demand_boom";
        setCrashMarkers((prev) =>
          mergeEventMarker(prev, {
            tickId: event.tick_id,
            label: isBoom ? "БУМ" : "ШОК",
            payload: event.payload ?? null,
          }),
        );
      }
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
      crashMarkers,
      macroState,
      activeShocks,
      workerState,
      connectionState,
      refPrice,
    }),
    [
      priceChartData,
      gmvChartData,
      backfillLoading,
      backfillError,
      highlightedSellerId,
      crashMarkers,
      macroState,
      activeShocks,
      workerState,
      connectionState,
      refPrice,
    ],
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
        setCrashMarkers([]);
        setMacroState(null);
        setActiveShocks([]);
        setRefPrice(null);
        void reloadBackfill();
      }

      setCyberLogBackfillKey((key) => key + 1);
    },
    [refresh, reloadBackfill, clearSeries, resetCyberLog],
  );

  const onShockQueued = useCallback(
    (body: SimulationShockRequest) => {
      const label = markerLabelForShock(body.shock_type);
      if (label === null) {
        return;
      }
      // Prefer last completed tick — matches WS event.tick_id more often than next-tick counter.
      const markerTick = Math.max(
        toLastCompletedTick(resolveSimulationTick(status, lastPayload)),
        0,
      );
      setCrashMarkers((prev) =>
        mergeEventMarker(prev, {
          tickId: markerTick,
          label,
          payload: null,
        }),
      );
    },
    [lastPayload, status],
  );

  return (
    <>
      {researchMode ? (
        <ResearchLab experimentId={researchId} summaryRows={researchRows} />
      ) : (
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
        macroRegime={macroState?.regime ?? null}
        macroState={macroState}
        activeShocks={activeShocks}
        onShockQueued={onShockQueued}
        onActionComplete={onActionComplete}
        cyberLogLines={cyberLogLines}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        asOfTick={asOfTick}
        pollAnalytics={pollAnalytics}
        pollMatrixLive={workerState === "RUNNING" && activeTab === "demand_matrix"}
        pollStrategyPulse={workerState === "RUNNING" && activeTab === "dynamics"}
        pollSegmentsLive={workerState === "RUNNING" && activeTab === "segments"}
        pollCategoriesLive={workerState === "RUNNING" && activeTab === "categories"}
        dynamics={dynamics}
        highlightedSellerId={highlightedSellerId}
        onHighlightSeller={setHighlightedSellerId}
      />
        </>
      )}
    </>
  );
}
