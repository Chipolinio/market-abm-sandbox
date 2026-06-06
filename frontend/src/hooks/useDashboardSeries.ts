import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchGmvByTick, fetchPriceIndex } from "@/api/analytics";
import type { GmvPoint, PriceIndexPoint, TickStreamPayload } from "@/api/types";
import {
  capSeries,
  downsampleForRender,
  renderCapForTier,
  seriesToSortedArray,
  toPriceChartData,
  upsertMergeByTickId,
  upsertTickPoint,
} from "@/state/chartSeries";
import type { GmvTickPoint, PriceChartRow, PriceTickPoint, TickSeries } from "@/state/types";

function priceFromIndex(p: PriceIndexPoint): PriceTickPoint {
  return {
    tick_id: p.tick_id,
    p10: p.p10,
    p50: p.p50,
    p90: p.p90,
    mean_price: p.mean_price,
  };
}

function gmvFromIndex(p: GmvPoint): GmvTickPoint {
  return {
    tick_id: p.tick_id,
    gmv: p.gmv,
    transaction_count: p.transaction_count,
  };
}

function priceFromPayload(payload: TickStreamPayload): PriceTickPoint | null {
  const q = payload.market_summary.price_quantiles;
  if (q === null) {
    return {
      tick_id: payload.tick_id,
      p10: null,
      p50: null,
      p90: null,
      mean_price: payload.market_summary.mean_price,
      timestamp_utc: payload.timestamp_utc,
    };
  }
  return {
    tick_id: payload.tick_id,
    p10: q.p10,
    p50: q.p50,
    p90: q.p90,
    mean_price: payload.market_summary.mean_price,
    timestamp_utc: payload.timestamp_utc,
  };
}

function gmvFromPayload(payload: TickStreamPayload): GmvTickPoint {
  return {
    tick_id: payload.tick_id,
    gmv: payload.market_summary.total_gmv,
    transaction_count: payload.market_summary.total_transactions,
    timestamp_utc: payload.timestamp_utc,
  };
}

export type UseDashboardSeriesResult = {
  priceChartData: PriceChartRow[];
  gmvChartData: GmvTickPoint[];
  totalGmv: number;
  driftAlerts: Array<Record<string, unknown>>;
  backfillLoading: boolean;
  backfillError: string | null;
  handlePayload: (payload: TickStreamPayload) => void;
  reloadBackfill: () => Promise<void>;
  clearSeries: () => void;
};

/** noop-step воркер шлёт миллионы тиков/сек — не засоряем графики. */
const NOOP_TICK_JUMP_THRESHOLD = 1000;
const SYNC_DEBOUNCE_MS = 2_000;

function downsampleIfNeeded<T extends { tick_id: number }>(data: T[]): T[] {
  const cap = renderCapForTier("macro");
  if (data.length <= cap) {
    return data;
  }
  return downsampleForRender(data, cap);
}

export function useDashboardSeries(): UseDashboardSeriesResult {
  const lastWsTickRef = useRef(-1);
  const syncTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const initialLoadDoneRef = useRef(false);
  const [priceSeries, setPriceSeries] = useState<TickSeries>(new Map());
  const [gmvSeries, setGmvSeries] = useState<TickSeries>(new Map());
  const [driftAlerts, setDriftAlerts] = useState<Array<Record<string, unknown>>>([]);
  const [backfillLoading, setBackfillLoading] = useState(true);
  const [backfillError, setBackfillError] = useState<string | null>(null);

  const clearSeries = useCallback(() => {
    lastWsTickRef.current = -1;
    initialLoadDoneRef.current = false;
    setPriceSeries(new Map());
    setGmvSeries(new Map());
    setDriftAlerts([]);
  }, []);

  const syncBackfill = useCallback(async () => {
    try {
      const [priceRes, gmvRes] = await Promise.all([fetchPriceIndex(), fetchGmvByTick()]);
      const pricePoints = priceRes.points.map(priceFromIndex);
      const gmvPoints = gmvRes.points.map(gmvFromIndex);

      setPriceSeries((prev) =>
        capSeries(upsertMergeByTickId(prev, pricePoints), "macro"),
      );
      setGmvSeries((prev) => capSeries(upsertMergeByTickId(prev, gmvPoints), "macro"));

      const maxTick = pricePoints.reduce((max, point) => Math.max(max, point.tick_id), -1);
      if (maxTick >= 0) {
        lastWsTickRef.current = Math.max(lastWsTickRef.current, maxTick);
      }
      setBackfillError(null);
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : "Backfill failed");
    }
  }, []);

  const scheduleSyncBackfill = useCallback(() => {
    if (syncTimerRef.current !== undefined) {
      clearTimeout(syncTimerRef.current);
    }
    syncTimerRef.current = setTimeout(() => {
      syncTimerRef.current = undefined;
      void syncBackfill();
    }, SYNC_DEBOUNCE_MS);
  }, [syncBackfill]);

  const reloadBackfill = useCallback(async () => {
    const showLoading = !initialLoadDoneRef.current;
    if (showLoading) {
      setBackfillLoading(true);
    }
    try {
      const [priceRes, gmvRes] = await Promise.all([fetchPriceIndex(), fetchGmvByTick()]);

      const pricePoints = priceRes.points.map(priceFromIndex);
      const gmvPoints = gmvRes.points.map(gmvFromIndex);

      setPriceSeries(capSeries(upsertMergeByTickId(new Map(), pricePoints), "macro"));
      setGmvSeries(capSeries(upsertMergeByTickId(new Map(), gmvPoints), "macro"));

      lastWsTickRef.current =
        pricePoints.length > 0 ? Math.max(...pricePoints.map((point) => point.tick_id)) : -1;

      initialLoadDoneRef.current = true;
      setBackfillError(null);
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : "Backfill failed");
    } finally {
      if (showLoading) {
        setBackfillLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    void reloadBackfill();
    return () => {
      if (syncTimerRef.current !== undefined) {
        clearTimeout(syncTimerRef.current);
      }
    };
  }, [reloadBackfill]);

  const handlePayload = useCallback(
    (payload: TickStreamPayload) => {
      const prev = lastWsTickRef.current;
      if (prev >= 0 && payload.tick_id - prev > NOOP_TICK_JUMP_THRESHOLD) {
        return;
      }
      const gap = prev >= 0 ? payload.tick_id - prev : 0;
      lastWsTickRef.current = payload.tick_id;

      if (gap > 1) {
        scheduleSyncBackfill();
      }

      const pricePoint = priceFromPayload(payload);
      if (pricePoint !== null) {
        setPriceSeries((prevSeries) => upsertTickPoint(prevSeries, pricePoint, "macro"));
      }
      setGmvSeries((prevSeries) => upsertTickPoint(prevSeries, gmvFromPayload(payload), "macro"));
      setDriftAlerts(payload.active_drift_alerts);
    },
    [scheduleSyncBackfill],
  );

  const priceSorted = useMemo(
    () => seriesToSortedArray(priceSeries) as PriceTickPoint[],
    [priceSeries],
  );
  const gmvSorted = useMemo(
    () => seriesToSortedArray(gmvSeries) as GmvTickPoint[],
    [gmvSeries],
  );

  const priceChartData = useMemo(
    () => downsampleIfNeeded(toPriceChartData(priceSorted)),
    [priceSorted],
  );

  const gmvChartData = useMemo(
    () => downsampleIfNeeded(gmvSorted),
    [gmvSorted],
  );

  const totalGmv = useMemo(
    () => gmvSorted.reduce((sum, p) => sum + p.gmv, 0),
    [gmvSorted],
  );

  return {
    priceChartData,
    gmvChartData,
    totalGmv,
    driftAlerts,
    backfillLoading,
    backfillError,
    handlePayload,
    reloadBackfill,
    clearSeries,
  };
}
