import { ControlPanel } from "@/components/ControlPanel";
import { DriftAlerts } from "@/components/DriftAlerts";
import { GmvChart } from "@/components/GmvChart";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";
import { StatusBar } from "@/components/StatusBar";
import { TopListingsSection } from "@/components/TopListingsSection";
import { useDashboardSeries } from "@/hooks/useDashboardSeries";
import { useSimulationStatus } from "@/hooks/useSimulationStatus";
import { useTickStream } from "@/hooks/useTickStream";
import { useTopListingsSeries } from "@/hooks/useTopListingsSeries";

export default function App() {
  const { status, refresh } = useSimulationStatus();
  const {
    priceChartData,
    gmvChartData,
    totalGmv,
    driftAlerts,
    backfillLoading,
    backfillError,
    handlePayload,
    reloadBackfill,
  } = useDashboardSeries();

  const { listings: topListings, loading: topListingsLoading, error: topListingsError, reload: reloadTopListings } =
    useTopListingsSeries();

  const { connectionState, reconnectAttempt, lastPayload } = useTickStream({
    onPayload: handlePayload,
  });

  // REST /status — источник истины для кнопок; WS worker_state дублирует после фикса backend.
  const workerState = status?.state ?? lastPayload?.worker_state ?? "IDLE";
  const showFailed =
    workerState === "FAILED" || (status?.last_error !== null && status?.last_error !== undefined);

  const onActionComplete = async (beforeState: typeof workerState) => {
    // START/PAUSE асинхронны в воркере — ждём смены state, не один мгновенный poll.
    for (let i = 0; i < 25; i += 1) {
      const next = await refresh();
      if (next !== null && next.state !== beforeState) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    void reloadBackfill();
    void reloadTopListings();
  };

  return (
    <div className="dashboard">
      <StatusBar
        status={status}
        wsState={lastPayload?.worker_state ?? null}
        connectionState={connectionState}
        reconnectAttempt={reconnectAttempt}
      />

      {showFailed ? (
        <div className="failed-banner" role="alert">
          Simulation failed: {status?.last_error ?? "see worker logs"}
        </div>
      ) : null}

      {backfillLoading ? <p className="backfill-status">Loading historical data…</p> : null}
      {backfillError !== null ? (
        <p className="backfill-status error">Backfill: {backfillError}</p>
      ) : null}
      {topListingsError !== null ? (
        <p className="backfill-status error">Top listings: {topListingsError}</p>
      ) : null}

      <ControlPanel
        state={workerState}
        totalGmv={totalGmv}
        onActionComplete={onActionComplete}
      />

      <div className="charts-grid">
        <div className="chart-card">
          <h2>Price Quantiles (p10 / p50 / p90)</h2>
          <PriceQuantileChart data={priceChartData} />
        </div>
        <div className="chart-card">
          <h2>GMV by Tick</h2>
          <GmvChart data={gmvChartData} />
        </div>
      </div>

      <TopListingsSection listings={topListings} loading={topListingsLoading} />

      <DriftAlerts alerts={driftAlerts} />
    </div>
  );
}
