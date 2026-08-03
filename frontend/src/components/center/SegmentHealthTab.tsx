import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSegmentHealth } from "@/api/analytics";
import type { SegmentRowDTO } from "@/types/observability";

type Props = {
  asOfTick: number;
  pollLive?: boolean;
};

const POLL_MS = 5_000;

/** Segment health table rich/standard/low (Spec 014 §7.1). */
export function SegmentHealthTab({ asOfTick, pollLive = false }: Props) {
  const [rows, setRows] = useState<SegmentRowDTO[]>([]);
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
      const resp = await fetchSegmentHealth(tickRef.current);
      if (!aliveRef.current) {
        return;
      }
      setRows(resp.rows);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "segments fetch failed");
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
    <div data-testid="segment-health-panel" className="flex h-full min-h-0 flex-col p-2">
      <h2 className="mb-2 shrink-0 text-xs uppercase tracking-wide text-muted">
        Segment health
      </h2>
      {loading && rows.length === 0 ? (
        <p className="text-xs text-muted">Загрузка сегментов…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
      {rows.length > 0 ? (
        <div className="min-h-0 flex-1 overflow-auto">
          <table className="w-full border-collapse text-left text-[11px]">
            <thead>
              <tr className="border-b border-border text-muted">
                <th className="py-1 pr-2">Segment</th>
                <th className="py-1 pr-2">Budget</th>
                <th className="py-1 pr-2">Freq</th>
                <th className="py-1 pr-2">Scar</th>
                <th className="py-1">Churn</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.segment} data-testid={`segment-row-${row.segment}`} className="border-b border-border/60">
                  <td className="py-1.5 pr-2 font-medium text-foreground">
                    {row.segment}{" "}
                    <span className="text-muted">
                      ({row.n_active}/{row.n_buyers})
                    </span>
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.mean_budget_effective.toFixed(1)}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.mean_freq_effective.toFixed(2)}
                  </td>
                  <td className="py-1.5 pr-2 font-mono">
                    {row.mean_scar_factor.toFixed(2)}
                  </td>
                  <td className="py-1.5 font-mono">
                    {(row.churn_share * 100).toFixed(0)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      {!loading && rows.length === 0 && error === null ? (
        <p className="text-xs text-muted">Нет данных сегментов</p>
      ) : null}
    </div>
  );
}
