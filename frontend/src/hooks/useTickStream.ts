import { useEffect, useRef, useState } from "react";

import { wsStreamUrl } from "@/api/config";
import type { TickStreamPayload } from "@/api/types";

export type ConnectionState = "connecting" | "open" | "closed" | "error";

export type UseTickStreamResult = {
  lastPayload: TickStreamPayload | null;
  connectionState: ConnectionState;
  reconnectAttempt: number;
};

export const WS_RECONNECT_BASE_MS = 1000;
export const WS_RECONNECT_CAP_MS = 30_000;

export type UseTickStreamOptions = {
  onPayload?: (payload: TickStreamPayload) => void;
  reconnectBaseMs?: number;
  reconnectCapMs?: number;
  WebSocketImpl?: typeof WebSocket;
  enabled?: boolean;
};

function nextBackoff(attempt: number, baseMs: number, capMs: number): number {
  return Math.min(baseMs * 2 ** attempt, capMs);
}

function parsePayload(raw: string): TickStreamPayload | null {
  try {
    const data = JSON.parse(raw) as TickStreamPayload;
    if (typeof data.tick_id !== "number") {
      return null;
    }
    return data;
  } catch {
    return null;
  }
}

export function useTickStream(options: UseTickStreamOptions = {}): UseTickStreamResult {
  const {
    onPayload,
    reconnectBaseMs = WS_RECONNECT_BASE_MS,
    reconnectCapMs = WS_RECONNECT_CAP_MS,
    WebSocketImpl = WebSocket,
    enabled = true,
  } = options;

  const onPayloadRef = useRef(onPayload);
  onPayloadRef.current = onPayload;

  const [lastPayload, setLastPayload] = useState<TickStreamPayload | null>(null);
  const [connectionState, setConnectionState] = useState<ConnectionState>("closed");
  const [reconnectAttempt, setReconnectAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) {
      setConnectionState("closed");
      return undefined;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    const openSocket = () => {
      if (disposed) {
        return;
      }
      setConnectionState("connecting");
      try {
        socket = new WebSocketImpl(wsStreamUrl());
      } catch {
        if (!disposed) {
          setConnectionState("error");
        }
        return;
      }

      socket.onopen = () => {
        if (disposed) {
          return;
        }
        attempt = 0;
        setReconnectAttempt(0);
        setConnectionState("open");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        if (disposed) {
          return;
        }
        const payload = parsePayload(event.data);
        if (payload === null) {
          return;
        }
        setLastPayload(payload);
        onPayloadRef.current?.(payload);
      };

      socket.onerror = () => {
        if (!disposed) {
          setConnectionState("error");
        }
      };

      socket.onclose = () => {
        if (disposed) {
          return;
        }
        setConnectionState("closed");
        const delay = nextBackoff(attempt, reconnectBaseMs, reconnectCapMs);
        attempt += 1;
        setReconnectAttempt(attempt);
        retryTimer = setTimeout(openSocket, delay);
      };
    };

    // Отложенный старт: React StrictMode (dev) сразу размонтирует эффект.
    const startTimer = setTimeout(openSocket, 0);

    return () => {
      disposed = true;
      clearTimeout(startTimer);
      if (retryTimer !== undefined) {
        clearTimeout(retryTimer);
      }
      if (socket !== null && socket.readyState === 0) {
        socket.onopen = null;
        socket.onclose = null;
        socket.onerror = null;
        socket.onmessage = null;
      }
      socket?.close();
    };
  }, [WebSocketImpl, enabled, reconnectBaseMs, reconnectCapMs]);

  return { lastPayload, connectionState, reconnectAttempt };
}
