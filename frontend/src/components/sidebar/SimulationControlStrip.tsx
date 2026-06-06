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
  onActionComplete: (beforeState: WorkerState) => Promise<void>;
};

export function SimulationControlStrip({ state, onActionComplete }: Props) {
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
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || state === "RUNNING" || state === "FAILED"}
          onClick={() => void onStart()}
        >
          Start
        </button>
        <button
          type="button"
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || state !== "RUNNING"}
          onClick={() => void run(pauseSimulation)}
        >
          Pause
        </button>
        <button
          type="button"
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || state !== "PAUSED"}
          onClick={() => void run(stepSimulation)}
        >
          Step
        </button>
        <button
          type="button"
          className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm disabled:opacity-50"
          disabled={busy || state === "RUNNING"}
          onClick={() => void run(resetSimulation)}
        >
          Reset
        </button>
      </div>
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
