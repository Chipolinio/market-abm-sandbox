import { EnvironmentConfigurator } from "@/components/sidebar/EnvironmentConfigurator";
import { MacroStatePanel } from "@/components/sidebar/MacroStatePanel";
import { ActiveShocksPanel } from "@/components/sidebar/ActiveShocksPanel";
import { ShocksControlPanel } from "@/components/sidebar/ShocksControlPanel";
import { SimulationControlStrip, type SimulationAction } from "@/components/sidebar/SimulationControlStrip";
import type { WorkerState } from "@/api/types";
import type { ActiveShockDTO, MacroStateDTO } from "@/types/macro";
import type { ConnectionState } from "@/types/ticker";
import type { SimulationShockRequest } from "@/types/shock";

export type ControlPanelProps = {
  workerState: WorkerState;
  onActionComplete: (beforeState: WorkerState, action: SimulationAction) => Promise<void>;
  onShockQueued?: (body: SimulationShockRequest) => void;
  macroState?: MacroStateDTO | null;
  activeShocks?: ActiveShockDTO[];
  connectionState?: ConnectionState;
};

/** Configure allowed only in IDLE / STOPPED (Spec 008 §4.4). */
export function isConfigurableWorkerState(state: WorkerState): boolean {
  return state === "IDLE" || state === "STOPPED";
}

export function ControlPanel({
  workerState,
  onActionComplete,
  onShockQueued,
  macroState = null,
  activeShocks = [],
  connectionState = "open",
}: ControlPanelProps) {
  const configurable = isConfigurableWorkerState(workerState);
  const runtimeLocked = workerState === "RUNNING" || workerState === "PAUSED";
  const shocksDisabled = workerState === "IDLE" || workerState === "STOPPED" || workerState === "FAILED";
  const shocksAccent = workerState === "RUNNING";

  return (
    <>
      <MacroStatePanel macro={macroState} connectionState={connectionState} />
      <ActiveShocksPanel shocks={activeShocks} connectionState={connectionState} />

      <section className="relative mb-6" data-testid="control-panel-environment">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-muted">
          Окружение
        </h2>
        <EnvironmentConfigurator disabled={!configurable} />
        {runtimeLocked ? (
          <div className="absolute inset-0 flex items-center justify-center rounded-md bg-white/75 backdrop-blur-[2px]">
            <div className="max-w-[15rem] rounded-md border border-border bg-white px-3 py-2 text-center text-xs text-muted-strong shadow-sm">
              Параметры заблокированы во время рантайма
            </div>
          </div>
        ) : null}
      </section>

      <section className="mb-6" data-testid="control-panel-shocks">
        <h2 className="mb-3 text-xs uppercase tracking-wider text-muted">
          Макро-шоки
        </h2>
        <ShocksControlPanel
          disabled={shocksDisabled}
          accent={shocksAccent}
          onShockQueued={onShockQueued}
        />
      </section>

      <section
        className="border-t border-border pt-4"
        data-testid="control-panel-simulation"
      >
        <SimulationControlStrip state={workerState} onActionComplete={onActionComplete} />
      </section>
    </>
  );
}
