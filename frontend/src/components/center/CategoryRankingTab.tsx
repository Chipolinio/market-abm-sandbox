import { useCallback, useEffect, useRef, useState } from "react";

import { fetchCategoryRanking } from "@/api/analytics";
import type { CategoryRankingRowDTO } from "@/types/observability";

type Props = {
  asOfTick: number;
  pollLive?: boolean;
};

const POLL_MS = 5_000;

/** Category ranking table (Spec 014 §7.2). */
export function CategoryRankingTab({ asOfTick, pollLive = false }: Props) {
  const [rows, setRows] = useState<CategoryRankingRowDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tickRef = useRef(asOfTick);
  const aliveRef = useRef(true);
  tickRef.current = asOfTick;

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await fetchCategoryRanking(tickRef.current);
      if (!aliveRef.current) {
        return;
      }
      setRows(resp.rows);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "category ranking fetch failed");
    } finally {
      if (aliveRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, asOfTick]);

  useEffect(() => {
    if (!pollLive) {
      return undefined;
    }
    const id = window.setInterval(() => {
      void refresh();
    }, POLL_MS);
    return () => window.clearInterval(id);
  }, [pollLive, refresh]);

  return (
    <div data-testid="category-ranking-panel" className="flex h-full min-h-0 flex-col p-2">
      <h2 className="mb-2 shrink-0 text-xs uppercase tracking-wide text-muted">
        Category ranking
      </h2>
      {loading && rows.length === 0 ? (
        <p className="text-xs text-muted">Загрузка категорий…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
      {rows.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead>
              <tr className="border-b border-border text-muted">
                <th className="py-1 pr-2">Cat</th>
                <th className="py-1 pr-2">N</th>
                <th className="py-1 pr-2">Med score</th>
                <th className="py-1 pr-2">Med price</th>
                <th className="py-1 pr-2">Sales Σ</th>
                <th className="py-1">Top listings</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.category_id}
                  data-testid={`category-row-${row.category_id}`}
                  className="border-b border-border/60"
                >
                  <td className="py-1.5 pr-2 font-medium text-foreground">
                    #{row.category_id}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">{row.n_listings}</td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.median_score.toFixed(3)}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.median_price.toFixed(1)}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.sales_window_sum.toFixed(1)}
                  </td>
                  <td className="py-1.5 font-mono text-muted-strong">
                    {row.top_listing_ids.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!loading && rows.length === 0 && error === null ? (
        <p className="text-xs text-muted">Нет данных категорий</p>
      ) : null}
    </div>
  );
}
