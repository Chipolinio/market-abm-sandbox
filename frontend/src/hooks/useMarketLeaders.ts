import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMarketLeaders } from "@/api/analytics";
import type { MarketLeaderRowDTO } from "@/types/leaders";

const POLL_INTERVAL_MS = 5_000;

export type UseMarketLeadersResult = {
  leaders: MarketLeaderRowDTO[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

export function useMarketLeaders(enabled: boolean, tickId: number): UseMarketLeadersResult {
  const [leaders, setLeaders] = useState<MarketLeaderRowDTO[]>([]);
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
      const response = await fetchMarketLeaders(tickIdRef.current, 5);
      if (!aliveRef.current) {
        return;
      }
      if (response.leaders.length > 0) {
        setLeaders(response.leaders);
      }
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Market leaders fetch failed");
    } finally {
      if (aliveRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    void refresh();
    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, refresh]);

  return { leaders, loading, error, refresh };
}
