import type { ReactNode } from "react";

import type { TickerRibbonProps } from "@/types/ticker";
import { formatCompactGmv } from "@/utils/formatCompactGmv";

function connectionDotClass(connectionState: TickerRibbonProps["connectionState"]): string {
  switch (connectionState) {
    case "open":
      return "bg-green-400";
    case "connecting":
      return "bg-amber-400";
    case "error":
      return "bg-red-400";
    default:
      return "bg-slate-400";
  }
}

function MetricCard({ children }: { children: ReactNode }) {
  return (
    <div
      data-testid="ticker-card"
      className="rounded border border-slate-700 bg-slate-800/50 px-3 py-1.5 text-sm"
    >
      {children}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div
      data-testid="ticker-skeleton"
      className="h-8 animate-pulse rounded border border-slate-700 bg-slate-800/50 px-3 py-1.5"
    />
  );
}

export function TickerRibbon({ metrics, connectionState }: TickerRibbonProps) {
  return (
    <div className="flex w-full flex-row items-center gap-4">
      <span
        data-testid="connection-dot"
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${connectionDotClass(connectionState)}`}
        aria-hidden
      />

      {metrics === null ? (
        <>
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </>
      ) : (
        <>
          <MetricCard>
            Active Sellers: {metrics.active_sellers_count}/{metrics.total_non_bankrupt_sellers}
          </MetricCard>
          <MetricCard>GMV: {formatCompactGmv(metrics.total_market_gmv)}</MetricCard>
          <MetricCard>Index: {metrics.market_price_index.toFixed(2)}</MetricCard>
          <MetricCard>t= {metrics.current_tick}</MetricCard>
        </>
      )}
    </div>
  );
}
