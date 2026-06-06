import { GmvChart } from "@/components/GmvChart";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";
import { TopListingsSection } from "@/components/TopListingsSection";
import type { DynamicsTabProps } from "@/components/center/types";

export function MarketDynamicsTab({
  priceChartData,
  gmvChartData,
  topListings,
  topListingsLoading,
  backfillLoading = false,
  backfillError = null,
}: DynamicsTabProps) {
  return (
    <div data-testid="market-dynamics-panel" className="flex flex-col gap-4">
      {backfillLoading ? <p className="text-sm text-slate-400">Loading historical data…</p> : null}
      {backfillError !== null ? (
        <p className="text-sm text-red-400">Backfill: {backfillError}</p>
      ) : null}

      <section className="rounded border border-slate-800 bg-slate-900/50 p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-300">Price Quantiles (p10 / p50 / p90)</h2>
        <PriceQuantileChart data={priceChartData} />
      </section>

      <section className="rounded border border-slate-800 bg-slate-900/50 p-4">
        <h2 className="mb-2 text-sm font-semibold text-slate-300">GMV by Tick</h2>
        <GmvChart data={gmvChartData} />
      </section>

      <TopListingsSection listings={topListings} loading={topListingsLoading} />
    </div>
  );
}
