import { EnvironmentConfigurator } from "@/components/sidebar/EnvironmentConfigurator";
import { ShocksControlPanel } from "@/components/sidebar/ShocksControlPanel";
import { SimulationControlStrip } from "@/components/sidebar/SimulationControlStrip";
import type { WorkerState } from "@/api/types";

export type ControlPanelProps = {
  workerState: WorkerState;
  onActionComplete: (beforeState: WorkerState) => Promise<void>;
};

/** Configure allowed only in IDLE / STOPPED (Spec 008 §4.4). */
export function isConfigurableWorkerState(state: WorkerState): boolean {
  return state === "IDLE" || state === "STOPPED";
}

export function ControlPanel({ workerState, onActionComplete }: ControlPanelProps) {
  const configurable = isConfigurableWorkerState(workerState);

  return (
    <>
      <section className="mb-6" data-testid="control-panel-environment">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Environment
        </h2>
        <EnvironmentConfigurator disabled={!configurable} />
      </section>

      <section className="mb-6" data-testid="control-panel-shocks">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Macro Shocks
        </h2>
        <ShocksControlPanel />
      </section>

      <section
        className="border-t border-slate-800 pt-4"
        data-testid="control-panel-simulation"
      >
        <SimulationControlStrip state={workerState} onActionComplete={onActionComplete} />
      </section>
    </>
  );
}
