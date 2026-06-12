import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMarketLeaders, TOP_SELLERS_RIBBON_LIMIT } from "@/api/analytics";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const POLL_INTERVAL_MS = 5_000;

export type UseTopSellersResult = {
  sellers: MarketLeaderRowDTO[];
  loading: boolean;
  error: string | null;
};

/** Top-3 sellers for Zone D ribbon. Polls while `live` (RUNNING/PAUSED). */
export function useTopSellers(tickId: number, live = true): UseTopSellersResult {
  const [sellers, setSellers] = useState<MarketLeaderRowDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tickIdRef = useRef(tickId);
  const aliveRef = useRef(true);
  tickIdRef.current = tickId;

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchMarketLeaders(tickIdRef.current, TOP_SELLERS_RIBBON_LIMIT);
      if (!aliveRef.current) {
        return;
      }
      if (response.leaders.length > 0) {
        setSellers(response.leaders);
      }
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Top sellers fetch failed");
    } finally {
      if (aliveRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (!live) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [live, refresh]);

  return { sellers, loading, error };
}
