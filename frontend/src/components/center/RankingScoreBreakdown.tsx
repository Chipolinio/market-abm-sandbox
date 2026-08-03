import { useEffect, useState } from "react";

import { fetchListingRanking } from "@/api/analytics";
import type { ListingRankingBreakdownDTO } from "@/types/observability";

export type RankingScoreBreakdownProps = {
  sellerId: number;
  tickId: number;
  enabled: boolean;
};

/** Expand seller → Score = w1×Rating + w2×(Pcat/P) + w3×log1p(Sales) (Spec 014 §6.2). */
export function RankingScoreBreakdown({
  sellerId,
  tickId,
  enabled,
}: RankingScoreBreakdownProps) {
  const [data, setData] = useState<ListingRankingBreakdownDTO | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!enabled) {
      setData(null);
      return undefined;
    }
    let alive = true;
    void fetchListingRanking(sellerId, tickId)
      .then((resp) => {
        if (alive) {
          setData(resp);
          setError(null);
        }
      })
      .catch((err: unknown) => {
        if (alive) {
          setData(null);
          setError(err instanceof Error ? err.message : "ranking fetch failed");
        }
      });
    return () => {
      alive = false;
    };
  }, [enabled, sellerId, tickId]);

  if (!enabled) {
    return null;
  }

  return (
    <div
      data-testid="ranking-score-breakdown"
      className="mt-2 rounded border border-dashed border-border bg-slate-50 p-2 text-[10px]"
      onClick={(event) => event.stopPropagation()}
    >
      {error !== null ? <p className="text-red-600">{error}</p> : null}
      {data === null && error === null ? (
        <p className="text-muted">Загрузка ranking…</p>
      ) : null}
      {data !== null ? (
        <>
          <p className="font-mono text-foreground">
            Score = {data.w1.toFixed(2)}×Rating + {data.w2.toFixed(2)}×(Pcat/P) +{" "}
            {data.w3.toFixed(2)}×log1p(Sales)
          </p>
          <p className="mt-1 text-muted-strong">
            = {data.term_rating.toFixed(3)} + {data.term_price.toFixed(3)} +{" "}
            {data.term_sales.toFixed(3)} → <span className="text-foreground">{data.score.toFixed(3)}</span>
          </p>
        </>
      ) : null}
    </div>
  );
}
