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

/**
 * REST fetch on tab focus only (Spec 009 §4.7 / P-4).
 * Re-fetch when `enabled` flips true (re-entry); NOT on every `tickId` update while mounted.
 */
export function useDemandMatrix(enabled: boolean, tickId: number): UseDemandMatrixResult {
  const [cells, setCells] = useState<DemandMatrixCellDTO[]>([]);
  const [gridSize, setGridSize] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tickIdRef = useRef(tickId);
  tickIdRef.current = tickId;

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchDemandMatrix(tickIdRef.current);
      setCells(response.cells);
      setGridSize(response.grid_size);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Demand matrix fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      return undefined;
    }

    void refresh();
    return undefined;
  }, [enabled, refresh]);

  return { cells, gridSize, loading, error, refresh };
}
