import type { ReactNode } from "react";

import type { TickerRibbonProps } from "@/types/ticker";
import { formatCompactGmv } from "@/utils/formatCompactGmv";

function connectionDotClass(connectionState: TickerRibbonProps["connectionState"]): string {
  switch (connectionState) {
    case "open":
      return "bg-emerald-600";
    case "connecting":
      return "bg-amber-600";
    case "error":
      return "bg-red-600";
    default:
      return "bg-muted";
  }
}

function priceTrendGlyph(delta: number): string {
  if (delta > 0) {
    return " ▲";
  }
  if (delta < 0) {
    return " ▼";
  }
  return "";
}

type MetricItemProps = {
  children: ReactNode;
  className?: string;
};

function MetricItem({ children, className }: MetricItemProps) {
  return (
    <div
      data-testid="ticker-card"
      className={`text-sm text-foreground${className ? ` ${className}` : ""}`}
    >
      {children}
    </div>
  );
}

function SkeletonItem() {
  return (
    <div
      data-testid="ticker-skeleton"
      className="h-5 w-24 animate-pulse bg-slate-100"
    />
  );
}

export function TickerRibbon({
  metrics,
  connectionState,
  priceIndexDelta = 0,
  flashCrashActive = false,
}: TickerRibbonProps) {
  return (
    <div className="flex w-full flex-row items-center gap-6">
      <span
        data-testid="connection-dot"
        className={`inline-block h-2 w-2 shrink-0 rounded-full ${connectionDotClass(connectionState)}`}
        aria-hidden
      />

      {metrics === null ? (
        <>
          <SkeletonItem />
          <SkeletonItem />
          <SkeletonItem />
          <SkeletonItem />
        </>
      ) : (
        <>
          <MetricItem>t= {metrics.current_tick}</MetricItem>
          <MetricItem>GMV: {formatCompactGmv(metrics.total_market_gmv)}</MetricItem>
          <MetricItem>
            Index: {metrics.market_price_index.toFixed(2)}
            {priceTrendGlyph(priceIndexDelta)}
          </MetricItem>
          <MetricItem
            className={flashCrashActive ? "animate-pulse text-red-600" : "text-muted-strong"}
          >
            {flashCrashActive ? "FLASH CRASH" : "STABLE"}
          </MetricItem>
        </>
      )}
    </div>
  );
}
