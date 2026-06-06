import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSystemEvents } from "@/api/analytics";
import {
  CYBER_LOG_MAX_LINES,
  prependEvents,
  toCyberLogLine,
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
const REST_BACKFILL_LIMIT = 200;

type UseCyberLogOptions = {
  /** Poll REST while simulation is active (WS batch may lag behind Parquet append). */
  pollWhileRunning?: boolean;
};

/**
 * Cyber-log: REST full sync on mount + incremental WS/poll merge.
 */
export function useCyberLog(
  wsEvents: SystemEventDTO[] | undefined,
  reconnectKey: number = 0,
  backfillKey: number = 0,
  options: UseCyberLogOptions = {},
): UseCyberLogResult {
  const { pollWhileRunning = false } = options;
  const [lines, setLines] = useState<CyberLogLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seenIdsRef = useRef(new Set<string>());
  const lastWsBatchRef = useRef("");

  const mergeEvents = useCallback((incoming: SystemEventDTO[]) => {
    if (incoming.length === 0) {
      return;
    }
    setLines((prev) =>
      prependEvents(prev, incoming, CYBER_LOG_MAX_LINES, seenIdsRef.current),
    );
  }, []);

  const replaceFromRest = useCallback((incoming: SystemEventDTO[]) => {
    seenIdsRef.current.clear();
    for (const event of incoming) {
      seenIdsRef.current.add(event.event_id);
    }
    setLines(incoming.slice(0, CYBER_LOG_MAX_LINES).map(toCyberLogLine));
  }, []);

  const reset = useCallback(() => {
    setLines([]);
    seenIdsRef.current.clear();
    lastWsBatchRef.current = "";
    setError(null);
  }, []);

  const pullFromRest = useCallback(
    async (mode: "replace" | "merge", showLoading: boolean) => {
      if (showLoading) {
        setLoading(true);
      }
      try {
        const response = await fetchSystemEvents(REST_BACKFILL_LIMIT);
        if (mode === "replace") {
          replaceFromRest(response.events);
        } else {
          mergeEvents(response.events);
        }
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "System events backfill failed");
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [mergeEvents, replaceFromRest],
  );

  useEffect(() => {
    let cancelled = false;

    const backfill = async () => {
      setLoading(true);
      try {
        const response = await fetchSystemEvents(REST_BACKFILL_LIMIT);
        if (cancelled) {
          return;
        }
        replaceFromRest(response.events);
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
  }, [reconnectKey, backfillKey, replaceFromRest]);

  useEffect(() => {
    if (wsEvents === undefined || wsEvents.length === 0) {
      return;
    }
    const signature = wsEvents.map((event) => event.event_id).join("|");
    if (signature === lastWsBatchRef.current) {
      return;
    }
    lastWsBatchRef.current = signature;
    mergeEvents(wsEvents);
  }, [wsEvents, mergeEvents]);

  useEffect(() => {
    if (!pollWhileRunning) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      void pullFromRest("merge", false);
    }, LIVE_POLL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [pollWhileRunning, pullFromRest]);

  return { lines, loading, error, reset };
};
