import { GmvChart } from "@/components/GmvChart";
import { PriceQuantileChart } from "@/components/PriceQuantileChart";
import type { DynamicsTabProps } from "@/components/center/types";

export function MarketDynamicsTab({
  priceChartData,
  gmvChartData,
  backfillLoading = false,
  backfillError = null,
  highlightedSellerId = null,
}: DynamicsTabProps) {
  return (
    <div
      data-testid="market-dynamics-panel"
      className="flex h-full min-h-0 flex-col gap-2"
    >
      {highlightedSellerId !== null ? (
        <p
          data-testid="highlighted-seller-banner"
          className="shrink-0 border-b border-border px-0 py-1 text-xs text-accent"
        >
          Подсветка тренда: селлер #{highlightedSellerId}
        </p>
      ) : null}
      {backfillLoading ? (
        <p className="shrink-0 text-xs text-muted">Загрузка истории…</p>
      ) : null}
      {backfillError !== null ? (
        <p className="shrink-0 text-xs text-red-600">Backfill: {backfillError}</p>
      ) : null}

      <section className="flex h-1/2 min-h-0 flex-col bg-white pb-2">
        <h2 className="mb-1 shrink-0 text-xs uppercase tracking-wide text-muted">
          Квантили цен (p10 / p50 / p90)
        </h2>
        <div className="min-h-0 flex-1">
          <PriceQuantileChart data={priceChartData} />
        </div>
      </section>

      <section className="flex h-1/2 min-h-0 flex-col bg-white pb-2">
        <h2 className="mb-1 shrink-0 text-xs uppercase tracking-wide text-muted">
          GMV по тикам
        </h2>
        <div className="min-h-0 flex-1">
          <GmvChart data={gmvChartData} />
        </div>
      </section>
    </div>
  );
}
