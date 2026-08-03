import { useState } from "react";

import { ApiError } from "@/api/client";
import { triggerShock } from "@/api/simulation";
import { MCK_BUTTON_MD, MCK_BUTTON_SHOCK_ACCENT } from "@/styles/mckinsey";
import type { CrisisScenario, SimulationShockRequest } from "@/types/shock";

const DEMAND_CRASH_BODY: SimulationShockRequest = {
  shock_type: "demand_crash",
  intensity: 1.0,
  scenario: "standard",
};

const MARKETPLACE_PROMOTION_BODY: SimulationShockRequest = {
  shock_type: "marketplace_promotion",
  intensity: 1.0,
  duration_ticks: 15,
};

const SCENARIO_OPTIONS: { value: CrisisScenario; label: string }[] = [
  { value: "mild", label: "Слабый спад" },
  { value: "standard", label: "Шок спроса" },
  { value: "severe", label: "Рецессия" },
];

function scenarioButtonLabel(scenario: CrisisScenario): string {
  const option = SCENARIO_OPTIONS.find((item) => item.value === scenario);
  return option ? `Запустить — ${option.label}` : "Запустить шок спроса";
}

type Props = {
  disabled?: boolean;
  accent?: boolean;
  onShockQueued?: (body: SimulationShockRequest) => void;
};

export function ShocksControlPanel({
  disabled = false,
  accent = false,
  onShockQueued,
}: Props) {
  const [scenario, setScenario] = useState<CrisisScenario>("standard");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runShock = async (body: SimulationShockRequest) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const response = await triggerShock(body);
      setMessage(`Шок в очереди (глубина=${response.queue_depth})`);
      onShockQueued?.(body);
    } catch (err) {
      const text =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Не удалось поставить шок";
      setError(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {disabled ? (
        <p className="rounded-md border border-border bg-slate-50 px-3 py-2 text-xs text-muted">
          Шоки доступны только после запуска симуляции.
        </p>
      ) : null}
      <label className="flex flex-col gap-1 text-xs text-muted">
        Сценарий шока
        <select
          className="border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          value={scenario}
          disabled={busy || disabled}
          onChange={(event) => setScenario(event.target.value as CrisisScenario)}
        >
          {SCENARIO_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className={accent ? MCK_BUTTON_SHOCK_ACCENT : MCK_BUTTON_MD}
        disabled={busy || disabled}
        onClick={() =>
          void runShock({
            ...DEMAND_CRASH_BODY,
            scenario,
          })
        }
      >
        {scenarioButtonLabel(scenario)}
      </button>
      <button
        type="button"
        className={MCK_BUTTON_MD}
        disabled={busy || disabled}
        onClick={() => void runShock(MARKETPLACE_PROMOTION_BODY)}
      >
        Принудительная акция маркетплейса
      </button>
      {message !== null ? <p className="text-xs text-emerald-700">{message}</p> : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
