import { GmvChart } from "@/components/GmvChart";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";
import type { DynamicsTabProps } from "@/components/center/types";

export function MarketDynamicsTab({
  priceChartData,
  gmvChartData,
  backfillLoading = false,
  backfillError = null,
}: DynamicsTabProps) {
  return (
    <div
      data-testid="market-dynamics-panel"
      className="flex h-full min-h-0 flex-col gap-2"
    >
      {backfillLoading ? (
        <p className="shrink-0 text-xs text-slate-500">Loading historical data…</p>
      ) : null}
      {backfillError !== null ? (
        <p className="shrink-0 text-xs text-red-400">Backfill: {backfillError}</p>
      ) : null}

      <section className="flex h-1/2 min-h-0 flex-col rounded border border-slate-800 bg-slate-900/60 p-2">
        <h2 className="mb-1 shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-400">
          Price Quantiles (p10 / p50 / p90)
        </h2>
        <div className="min-h-0 flex-1">
          <PriceQuantileChart data={priceChartData} />
        </div>
      </section>

      <section className="flex h-1/2 min-h-0 flex-col rounded border border-slate-800 bg-slate-900/60 p-2">
        <h2 className="mb-1 shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-400">
          GMV by Tick
        </h2>
        <div className="min-h-0 flex-1">
          <GmvChart data={gmvChartData} />
        </div>
      </section>
    </div>
  );
}
