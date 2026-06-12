import { useCallback, useEffect, useRef, useState } from "react";

import { fetchTopListings } from "@/api/analytics";
import type { ListingSeriesData } from "@/state/types";

export type UseTopListingsSeriesResult = {
  listings: ListingSeriesData[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
};

export function useTopListingsSeries(enabled: boolean = true): UseTopListingsSeriesResult {
  const [listings, setListings] = useState<ListingSeriesData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchTopListings();
      if (!aliveRef.current) {
        return;
      }
      setListings(response.listings);
      setError(null);
    } catch (err) {
      if (!aliveRef.current) {
        return;
      }
      setError(err instanceof Error ? err.message : "Top listings backfill failed");
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

    void reload();
    return undefined;
  }, [enabled, reload]);

  return { listings, loading, error, reload };
}
