// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useTickStream } from "@/hooks/useTickStream";

type MockHandler = (() => void) | null;

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onopen: MockHandler = null;
  onclose: MockHandler = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: MockHandler = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
    queueMicrotask(() => this.onopen?.());
  }

  close() {
    queueMicrotask(() => this.onclose?.());
  }

  send() {
    // server ignores client messages
  }
}

describe("useTickStream", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reconnects_on_close", async () => {
    const { result } = renderHook(() =>
      useTickStream({
        WebSocketImpl: MockWebSocket as unknown as typeof WebSocket,
        reconnectBaseMs: 50,
        reconnectCapMs: 200,
      }),
    );

    await act(async () => {
      vi.advanceTimersByTime(0);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(result.current.connectionState).toBe("open");

    await act(async () => {
      MockWebSocket.instances[0]!.close();
      await Promise.resolve();
    });

    expect(result.current.connectionState).toBe("closed");
    expect(result.current.reconnectAttempt).toBe(1);

    await act(async () => {
      vi.advanceTimersByTime(50);
      await Promise.resolve();
    });

    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2);
  });
});
