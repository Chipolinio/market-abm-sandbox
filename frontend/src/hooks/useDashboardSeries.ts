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
};

/** noop-step воркер шлёт миллионы тиков/сек — не засоряем графики. */
const NOOP_TICK_JUMP_THRESHOLD = 1000;

export function useDashboardSeries(): UseDashboardSeriesResult {
  const lastWsTickRef = useRef(-1);
  const [priceSeries, setPriceSeries] = useState<TickSeries>(new Map());
  const [gmvSeries, setGmvSeries] = useState<TickSeries>(new Map());
  const [driftAlerts, setDriftAlerts] = useState<Array<Record<string, unknown>>>([]);
  const [backfillLoading, setBackfillLoading] = useState(true);
  const [backfillError, setBackfillError] = useState<string | null>(null);

  const reloadBackfill = useCallback(async () => {
    setBackfillLoading(true);
    try {
      const [priceRes, gmvRes] = await Promise.all([fetchPriceIndex(), fetchGmvByTick()]);

      const pricePoints = priceRes.points.map(priceFromIndex);
      const gmvPoints = gmvRes.points.map(gmvFromIndex);

      setPriceSeries((prev) =>
        capSeries(
          upsertMergeByTickId(prev, pricePoints, { rejectBelowMax: true }),
          "macro",
        ),
      );

      setGmvSeries((prev) =>
        capSeries(upsertMergeByTickId(prev, gmvPoints, { rejectBelowMax: true }), "macro"),
      );

      setBackfillError(null);
    } catch (err) {
      setBackfillError(err instanceof Error ? err.message : "Backfill failed");
    } finally {
      setBackfillLoading(false);
    }
  }, []);

  useEffect(() => {
    void reloadBackfill();
  }, [reloadBackfill]);

  const handlePayload = useCallback((payload: TickStreamPayload) => {
    const prev = lastWsTickRef.current;
    if (prev >= 0 && payload.tick_id - prev > NOOP_TICK_JUMP_THRESHOLD) {
      return;
    }
    lastWsTickRef.current = payload.tick_id;

    const pricePoint = priceFromPayload(payload);
    if (pricePoint !== null) {
      setPriceSeries((prev) => upsertTickPoint(prev, pricePoint, "macro"));
    }
    setGmvSeries((prev) => upsertTickPoint(prev, gmvFromPayload(payload), "macro"));
    setDriftAlerts(payload.active_drift_alerts);
  }, []);

  const priceSorted = useMemo(
    () => seriesToSortedArray(priceSeries) as PriceTickPoint[],
    [priceSeries],
  );
  const gmvSorted = useMemo(
    () => seriesToSortedArray(gmvSeries) as GmvTickPoint[],
    [gmvSeries],
  );

  const priceChartData = useMemo(
    () =>
      downsampleForRender(toPriceChartData(priceSorted), renderCapForTier("macro")),
    [priceSorted],
  );

  const gmvChartData = useMemo(
    () => downsampleForRender(gmvSorted, renderCapForTier("macro")),
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
  };
}
