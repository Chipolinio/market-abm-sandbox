import { useCallback, useEffect, useRef, useState } from "react";

import { fetchStrategyPulse } from "@/api/analytics";
import type { StrategyPulseResponse } from "@/types/observability";

export type UseStrategyPulseResult = {
  pulse: StrategyPulseResponse | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const POLL_LIVE_MS = 5_000;

/** REST strategy pulse for Dynamics tab (Spec 014 §6.1). */
export function useStrategyPulse(
  enabled: boolean,
  tickId?: number,
  pollLive = false,
): UseStrategyPulseResult {
  const [pulse, setPulse] = useState<StrategyPulseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tickRef = useRef(tickId);
  const aliveRef = useRef(true);
  tickRef.current = tickId;

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchStrategyPulse(tickRef.current);
      if (!aliveRef.current) {
        return;
      }
      setPulse(response);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "strategy pulse fetch failed");
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
    return undefined;
  }, [enabled, refresh, tickId]);

  useEffect(() => {
    if (!enabled || !pollLive) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void refresh();
    }, POLL_LIVE_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [enabled, pollLive, refresh]);

  return { pulse, loading, error, refresh };
}
