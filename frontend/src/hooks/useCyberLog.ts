import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSystemEvents } from "@/api/analytics";
import {
  CYBER_LOG_MAX_LINES,
  prependEvents,
  type CyberLogLine,
} from "@/state/cyberLog";
import type { SystemEventDTO } from "@/types/events";

export type UseCyberLogResult = {
  lines: CyberLogLine[];
  loading: boolean;
  error: string | null;
  reset: () => void;
};

const LIVE_POLL_MS = 3_000;

type UseCyberLogOptions = {
  /** Poll REST while simulation is RUNNING (WS batch may lag behind Parquet append). */
  pollWhileRunning?: boolean;
  /** Current stream tick — re-process WS batch when it advances. */
  streamTickId?: number;
};

/**
 * Cyber-log: REST backfill on mount/reconnect/refresh + WS prepend + live poll while RUNNING.
 */
export function useCyberLog(
  wsEvents: SystemEventDTO[] | undefined,
  reconnectKey: number = 0,
  backfillKey: number = 0,
  options: UseCyberLogOptions = {},
): UseCyberLogResult {
  const { pollWhileRunning = false, streamTickId = 0 } = options;
  const [lines, setLines] = useState<CyberLogLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seenIdsRef = useRef(new Set<string>());

  const mergeEvents = useCallback((incoming: SystemEventDTO[]) => {
    if (incoming.length === 0) {
      return;
    }
    setLines((prev) =>
      prependEvents(prev, incoming, CYBER_LOG_MAX_LINES, seenIdsRef.current),
    );
  }, []);

  const reset = useCallback(() => {
    setLines([]);
    seenIdsRef.current.clear();
    setError(null);
  }, []);

  const pullFromRest = useCallback(async (showLoading: boolean) => {
    if (showLoading) {
      setLoading(true);
    }
    try {
      const response = await fetchSystemEvents(50);
      mergeEvents(response.events);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "System events backfill failed");
    } finally {
      if (showLoading) {
        setLoading(false);
      }
    }
  }, [mergeEvents]);

  useEffect(() => {
    let cancelled = false;

    const backfill = async () => {
      setLoading(true);
      try {
        const response = await fetchSystemEvents(50);
        if (cancelled) {
          return;
        }
        mergeEvents(response.events);
        setError(null);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "System events backfill failed");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void backfill();

    return () => {
      cancelled = true;
    };
  }, [reconnectKey, backfillKey, mergeEvents]);

  useEffect(() => {
    if (wsEvents === undefined || wsEvents.length === 0) {
      return;
    }
    mergeEvents(wsEvents);
  }, [wsEvents, streamTickId, mergeEvents]);

  useEffect(() => {
    if (!pollWhileRunning) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void pullFromRest(false);
    }, LIVE_POLL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [pollWhileRunning, pullFromRest]);

  return { lines, loading, error, reset };
}
