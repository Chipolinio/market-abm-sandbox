import { useCallback, useEffect, useState } from "react";

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

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetchTopListings();
      setListings(response.listings);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Top listings backfill failed");
    } finally {
      setLoading(false);
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
