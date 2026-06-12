import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDemandMatrix } from "@/api/analytics";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";

export type UseDemandMatrixResult = {
  cells: DemandMatrixCellDTO[];
  gridSize: number;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const POLL_LIVE_MS = 5_000;

/**
 * REST fetch on tab focus (Spec 009 §4.7 / P-4).
 * Optional live poll while tab is open and simulation is RUNNING.
 */
export function useDemandMatrix(
  enabled: boolean,
  tickId: number,
  pollLive = false,
): UseDemandMatrixResult {
  const [cells, setCells] = useState<DemandMatrixCellDTO[]>([]);
  const [gridSize, setGridSize] = useState(10);
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
      const response = await fetchDemandMatrix(tickIdRef.current);
      if (!aliveRef.current) {
        return;
      }
      setCells(response.cells);
      setGridSize(response.grid_size);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Demand matrix fetch failed");
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
  }, [enabled, refresh]);

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

  return { cells, gridSize, loading, error, refresh };
}
