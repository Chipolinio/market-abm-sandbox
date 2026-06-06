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

/**
 * Cyber-log state: REST backfill on mount/reconnect + WS prepend (Spec 009 §4.8 / P-3).
 *
 * @param wsEvents — `TickStreamPayload.events` from 1 Hz stream
 * @param reconnectKey — increment (e.g. `reconnectAttempt`) to trigger REST backfill again
 */
export function useCyberLog(
  wsEvents: SystemEventDTO[] | undefined,
  reconnectKey: number = 0,
): UseCyberLogResult {
  const [lines, setLines] = useState<CyberLogLine[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seenIdsRef = useRef(new Set<string>());

  const reset = useCallback(() => {
    setLines([]);
    seenIdsRef.current.clear();
    setError(null);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const backfill = async () => {
      setLoading(true);
      try {
        const response = await fetchSystemEvents(50);
        if (cancelled) {
          return;
        }
        setLines((prev) =>
          prependEvents(prev, response.events, CYBER_LOG_MAX_LINES, seenIdsRef.current),
        );
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
  }, [reconnectKey]);

  useEffect(() => {
    if (wsEvents === undefined || wsEvents.length === 0) {
      return;
    }

    setLines((prev) =>
      prependEvents(prev, wsEvents, CYBER_LOG_MAX_LINES, seenIdsRef.current),
    );
  }, [wsEvents]);

  return { lines, loading, error, reset };
}
