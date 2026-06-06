import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMarketLeaders } from "@/api/analytics";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const POLL_INTERVAL_MS = 5_000;

export type UseTopSellersResult = {
  sellers: MarketLeaderRowDTO[];
  loading: boolean;
  error: string | null;
};

/** Top-3 sellers for Zone D ribbon (polls while mounted). */
export function useTopSellers(tickId: number): UseTopSellersResult {
  const [sellers, setSellers] = useState<MarketLeaderRowDTO[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tickIdRef = useRef(tickId);
  tickIdRef.current = tickId;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchMarketLeaders(tickIdRef.current, 3);
      if (response.leaders.length > 0) {
        setSellers(response.leaders);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Top sellers fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [refresh, tickId]);

  return { sellers, loading, error };
}
