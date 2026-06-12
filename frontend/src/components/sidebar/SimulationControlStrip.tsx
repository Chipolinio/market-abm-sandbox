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
import { MCK_BUTTON } from "@/styles/mckinsey";

export type SimulationAction = "start" | "pause" | "step" | "reset";

type Props = {
  state: WorkerState;
  onActionComplete: (beforeState: WorkerState, action: SimulationAction) => Promise<void>;
};

export function SimulationControlStrip({ state, onActionComplete }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (action: () => Promise<unknown>, actionKind: SimulationAction) => {
    const beforeState = state;
    setBusy(true);
    setError(null);
    try {
      await action();
      await onActionComplete(beforeState, actionKind);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Action failed";
      setError(message);
    } finally {
      setBusy(false);
    }
  };

  const onStart = () =>
    run(
      () =>
        startSimulation({
          force_clear: isTerminalState(state),
        }),
      "start",
    );

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={MCK_BUTTON}
          disabled={busy || state === "RUNNING" || state === "FAILED"}
          onClick={() => void onStart()}
        >
          Старт
        </button>
        <button
          type="button"
          className={MCK_BUTTON}
          disabled={busy || state !== "RUNNING"}
          onClick={() => void run(pauseSimulation, "pause")}
        >
          Пауза
        </button>
        <button
          type="button"
          className={MCK_BUTTON}
          disabled={busy || state !== "PAUSED"}
          onClick={() => void run(stepSimulation, "step")}
        >
          Шаг
        </button>
        <button
          type="button"
          className={MCK_BUTTON}
          disabled={busy || state === "RUNNING"}
          onClick={() => void run(resetSimulation, "reset")}
        >
          Сброс
        </button>
      </div>
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
