import { useState } from "react";

import { ApiError } from "@/api/client";
import {
  isTerminalState,
  pauseSimulation,
  resetSimulation,
  startSimulation,
  stepSimulation,
} from "@/api/simulation";
import type { WorkerState } from "@/api/types";

type Props = {
  state: WorkerState;
  totalGmv: number;
  onActionComplete: (beforeState: WorkerState) => Promise<void>;
};

function formatGmv(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}k`;
  }
  return value.toFixed(0);
}

export function ControlPanel({ state, totalGmv, onActionComplete }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>) => {
    const beforeState = state;
    setBusy(true);
    setError(null);
    try {
      await action();
      await onActionComplete(beforeState);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Action failed";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const onStart = () =>
    run(() =>
      startSimulation({
        force_clear: isTerminalState(state),
      }),
    );

  return (
    <section className="control-panel">
      <div className="control-buttons">
        <button
          type="button"
          disabled={busy || state === "RUNNING" || state === "FAILED"}
          onClick={() => void onStart()}
        >
          Start
        </button>
        <button
          type="button"
          disabled={busy || state !== "RUNNING"}
          onClick={() => void run(pauseSimulation)}
        >
          Pause
        </button>
        <button
          type="button"
          disabled={busy || state !== "PAUSED"}
          onClick={() => void run(stepSimulation)}
        >
          Step
        </button>
        <button
          type="button"
          disabled={busy || state === "RUNNING"}
          onClick={() => void run(resetSimulation)}
        >
          Reset
        </button>
      </div>
      <div className="control-summary">GMV Σ: {formatGmv(totalGmv)}</div>
      {error !== null ? <p className="control-error">{error}</p> : null}
    </section>
  );
}
