import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSimulationStatus } from "@/api/simulation";
import type { SimulationStatus } from "@/api/types";

const POLL_IDLE_MS = 5000;
const POLL_RUNNING_MS = 1000;

export type UseSimulationStatusResult = {
  status: SimulationStatus | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<SimulationStatus | null>;
};

export function useSimulationStatus(poll = true): UseSimulationStatusResult {
  const [status, setStatus] = useState<SimulationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const refresh = useCallback(async (): Promise<SimulationStatus | null> => {
    try {
      const next = await fetchSimulationStatus();
      if (!aliveRef.current) {
        return null;
      }
      setStatus(next);
      setError(null);
      return next;
    } catch (err) {
      if (!aliveRef.current) {
        return null;
      }
      setError(err instanceof Error ? err.message : "Status fetch failed");
      return null;
    } finally {
      if (aliveRef.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    if (!poll) {
      return undefined;
    }
    const intervalMs = status?.state === "RUNNING" ? POLL_RUNNING_MS : POLL_IDLE_MS;
    const id = setInterval(() => {
      void refresh();
    }, intervalMs);
    return () => clearInterval(id);
  }, [poll, refresh, status?.state]);

  return { status, loading, error, refresh };
}
