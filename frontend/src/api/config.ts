const DEV_API_DEFAULT = "http://localhost:8000";

/** API / WS base URLs (Spec 007 §8). */
export function apiBaseUrl(): string {
  const base =
    import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? DEV_API_DEFAULT : "");
  return base.replace(/\/$/, "");
}

export function wsBaseUrl(): string {
  const explicit = import.meta.env.VITE_WS_BASE_URL;
  if (explicit) {
    return explicit.replace(/\/$/, "");
  }
  const api = apiBaseUrl();
  if (api.startsWith("http://")) {
    return `ws://${api.slice("http://".length)}`;
  }
  if (api.startsWith("https://")) {
    return `wss://${api.slice("https://".length)}`;
  }
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}`;
  }
  return "ws://localhost:8000";
}

export function wsStreamUrl(): string {
  return `${wsBaseUrl()}/api/v1/stream/ws`;
}
