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
import { toLastCompletedTick } from "@/utils/analyticsTick";

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

function priceFromPayload(payload: TickStreamPayload, chartTickId: number): PriceTickPoint | null {
  const q = payload.market_summary.price_quantiles;
  if (q === null) {
    return {
      tick_id: chartTickId,
      p10: null,
      p50: null,
      p90: null,
      mean_price: payload.market_summary.mean_price,
      timestamp_utc: payload.timestamp_utc,
    };
  }
  return {
    tick_id: chartTickId,
    p10: q.p10,
    p50: q.p50,
    p90: q.p90,
    mean_price: payload.market_summary.mean_price,
    timestamp_utc: payload.timestamp_utc,
  };
}

function gmvFromPayload(payload: TickStreamPayload, chartTickId: number): GmvTickPoint {
  return {
    tick_id: chartTickId,
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
  reloadBackfill: () => Promise<boolean>;
  clearSeries: () => void;
};

/** noop-step воркер шлёт миллионы тиков/сек — не засоряем графики. */
const NOOP_TICK_JUMP_THRESHOLD = 1000;
const LIVE_SYNC_MS = 2_500;

function isLikelyStubPayload(payload: TickStreamPayload): boolean {
  const summary = payload.market_summary;
  return (
    summary.mean_price === 0 &&
    summary.total_gmv === 0 &&
    summary.total_transactions === 0 &&
    summary.price_quantiles === null
  );
}

function downsampleIfNeeded<T extends { tick_id: number }>(data: T[]): T[] {
  const cap = renderCapForTier("macro");
  if (data.length <= cap) {
    return data;
  }
  return downsampleForRender(data, cap);
}

export function useDashboardSeries(
  liveSync = false,
  reconnectKey: number = 0,
): UseDashboardSeriesResult {
  const lastWsTickRef = useRef(-1);
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

  const syncBackfill = useCallback(async (mode: "incremental" | "full" = "incremental") => {
    try {
      const [priceRes, gmvRes] = await Promise.all([fetchPriceIndex(), fetchGmvByTick()]);
      const pricePoints = priceRes.points.map(priceFromIndex);
      const gmvPoints = gmvRes.points.map(gmvFromIndex);

      if (pricePoints.length === 0 && gmvPoints.length === 0) {
        return;
      }

      const mergeOptions =
        mode === "incremental" ? { rejectBelowMax: true as const } : undefined;

      setPriceSeries((prev) =>
        capSeries(upsertMergeByTickId(prev, pricePoints, mergeOptions), "macro"),
      );
      setGmvSeries((prev) =>
        capSeries(upsertMergeByTickId(prev, gmvPoints, mergeOptions), "macro"),
      );

      const maxPriceTick = pricePoints.reduce((max, point) => Math.max(max, point.tick_id), -1);
      const maxGmvTick = gmvPoints.reduce((max, point) => Math.max(max, point.tick_id), -1);
      const maxTick = Math.max(maxPriceTick, maxGmvTick);
      if (maxTick >= 0) {
        lastWsTickRef.current = Math.max(lastWsTickRef.current, maxTick);
      }
      setBackfillError(null);
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : "Backfill failed");
    }
  }, []);

  const reloadBackfill = useCallback(async (): Promise<boolean> => {
    const showLoading = !initialLoadDoneRef.current;
    if (showLoading) {
      setBackfillLoading(true);
    }
    try {
      const [priceRes, gmvRes] = await Promise.all([fetchPriceIndex(), fetchGmvByTick()]);

      const pricePoints = priceRes.points.map(priceFromIndex);
      const gmvPoints = gmvRes.points.map(gmvFromIndex);

      if (pricePoints.length === 0 && gmvPoints.length === 0) {
        setBackfillError(null);
        return false;
      }

      setPriceSeries(capSeries(upsertMergeByTickId(new Map(), pricePoints), "macro"));
      setGmvSeries(capSeries(upsertMergeByTickId(new Map(), gmvPoints), "macro"));

      const maxPriceTick =
        pricePoints.length > 0 ? Math.max(...pricePoints.map((point) => point.tick_id)) : -1;
      const maxGmvTick =
        gmvPoints.length > 0 ? Math.max(...gmvPoints.map((point) => point.tick_id)) : -1;
      lastWsTickRef.current = Math.max(maxPriceTick, maxGmvTick);

      initialLoadDoneRef.current = true;
      setBackfillError(null);
      return true;
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : "Backfill failed");
      return false;
    } finally {
      if (showLoading) {
        setBackfillLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadWithRetry = async () => {
      for (let attempt = 0; attempt < 4; attempt += 1) {
        const loaded = await reloadBackfill();
        if (loaded || cancelled) {
          return;
        }
        await new Promise((resolve) => {
          window.setTimeout(resolve, 600);
        });
      }
    };

    void loadWithRetry();

    return () => {
      cancelled = true;
    };
  }, [reloadBackfill, reconnectKey]);

  useEffect(() => {
    if (!liveSync) {
      return undefined;
    }
    const intervalId = window.setInterval(() => {
      void syncBackfill("incremental");
    }, LIVE_SYNC_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [liveSync, syncBackfill]);

  const handlePayload = useCallback(
    (payload: TickStreamPayload) => {
      if (isLikelyStubPayload(payload) && payload.tick_id > 1) {
        return;
      }

      const chartTickId = toLastCompletedTick(payload.tick_id);
      const prev = lastWsTickRef.current;
      if (prev >= 0 && payload.tick_id - prev > NOOP_TICK_JUMP_THRESHOLD) {
        return;
      }
      if (chartTickId < prev) {
        return;
      }

      lastWsTickRef.current = Math.max(prev, chartTickId);

      const pricePoint = priceFromPayload(payload, chartTickId);
      if (pricePoint !== null) {
        setPriceSeries((prevSeries) => upsertTickPoint(prevSeries, pricePoint, "macro"));
      }
      setGmvSeries((prevSeries) =>
        upsertTickPoint(prevSeries, gmvFromPayload(payload, chartTickId), "macro"),
      );
      setDriftAlerts(payload.active_drift_alerts);
    },
    [],
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
};
