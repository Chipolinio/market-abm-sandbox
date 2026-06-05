import type { ConnectionState } from "@/hooks/useTickStream";

type Props = {
  state: ConnectionState;
  reconnectAttempt: number;
};

const LABELS: Record<ConnectionState, string> = {
  connecting: "Connecting…",
  open: "Connected",
  closed: "Reconnecting…",
  error: "Connection error",
};

const COLORS: Record<ConnectionState, string> = {
  connecting: "#b8860b",
  open: "#2e7d32",
  closed: "#b8860b",
  error: "#c62828",
};

export function ConnectionBadge({ state, reconnectAttempt }: Props) {
  const label =
    state === "closed" && reconnectAttempt > 0
      ? `${LABELS[state]} (#${reconnectAttempt})`
      : LABELS[state];

  return (
    <span className="connection-badge" style={{ color: COLORS[state] }}>
      <span className="connection-dot" style={{ background: COLORS[state] }} />
      {label}
    </span>
  );
}
