import { useState } from "react";

import { ApiError } from "@/api/client";
import { triggerShock } from "@/api/simulation";
import { MCK_BUTTON_MD, MCK_BUTTON_SHOCK_ACCENT, MCK_SECTION_TITLE } from "@/styles/mckinsey";
import type { CrisisScenario, SimulationShockRequest } from "@/types/shock";

const DEMAND_CRASH_BODY: SimulationShockRequest = {
  shock_type: "demand_crash",
  intensity: 1.0,
  scenario: "standard",
};

const DEMAND_BOOM_BODY: SimulationShockRequest = {
  shock_type: "demand_boom",
  intensity: 1.0,
  scenario: "standard",
};

const MARKETPLACE_PROMOTION_BODY: SimulationShockRequest = {
  shock_type: "marketplace_promotion",
  intensity: 1.0,
  duration_ticks: 15,
};

const PLATFORM_FEE_CUT_BODY: SimulationShockRequest = {
  shock_type: "platform_fee_cut",
  intensity: 1.0,
};

const CRASH_SCENARIO_OPTIONS: { value: CrisisScenario; label: string }[] = [
  { value: "mild", label: "Слабый спад" },
  { value: "standard", label: "Шок спроса" },
  { value: "severe", label: "Рецессия" },
];

const BOOM_SCENARIO_OPTIONS: { value: CrisisScenario; label: string }[] = [
  { value: "mild", label: "Оживление" },
  { value: "standard", label: "Сезонный бум" },
  { value: "severe", label: "Ажиотаж" },
];

function crashButtonLabel(scenario: CrisisScenario): string {
  const option = CRASH_SCENARIO_OPTIONS.find((item) => item.value === scenario);
  return option ? `Запустить — ${option.label}` : "Запустить шок спроса";
}

function boomButtonLabel(scenario: CrisisScenario): string {
  const option = BOOM_SCENARIO_OPTIONS.find((item) => item.value === scenario);
  return option ? `Запустить — ${option.label}` : "Запустить бум спроса";
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
  const [crashScenario, setCrashScenario] = useState<CrisisScenario>("standard");
  const [boomScenario, setBoomScenario] = useState<CrisisScenario>("standard");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runShock = async (body: SimulationShockRequest) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const response = await triggerShock(body);
      setMessage(`Событие в очереди (глубина=${response.queue_depth})`);
      onShockQueued?.(body);
    } catch (err) {
      const text =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Не удалось поставить событие";
      setError(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {disabled ? (
        <p className="rounded-md border border-border bg-slate-50 px-3 py-2 text-xs text-muted">
          События доступны только после запуска симуляции.
        </p>
      ) : null}

      {/* ── Negative demand ──────────────────────────────────── */}
      <p className={MCK_SECTION_TITLE}>Спад спроса</p>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Сценарий
        <select
          data-testid="crash-scenario-select"
          className="border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          value={crashScenario}
          disabled={busy || disabled}
          onChange={(e) => setCrashScenario(e.target.value as CrisisScenario)}
        >
          {CRASH_SCENARIO_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        data-testid="trigger-crash-btn"
        className={accent ? MCK_BUTTON_SHOCK_ACCENT : MCK_BUTTON_MD}
        disabled={busy || disabled}
        onClick={() => void runShock({ ...DEMAND_CRASH_BODY, scenario: crashScenario })}
      >
        {crashButtonLabel(crashScenario)}
      </button>

      {/* ── Positive demand ──────────────────────────────────── */}
      <p className={MCK_SECTION_TITLE}>Рост спроса</p>
      <label className="flex flex-col gap-1 text-xs text-muted">
        Сценарий
        <select
          data-testid="boom-scenario-select"
          className="border border-border bg-background px-2 py-1.5 text-sm text-foreground"
          value={boomScenario}
          disabled={busy || disabled}
          onChange={(e) => setBoomScenario(e.target.value as CrisisScenario)}
        >
          {BOOM_SCENARIO_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        data-testid="trigger-boom-btn"
        className="border border-border bg-emerald-50 px-3 py-2 text-sm text-emerald-800 hover:bg-emerald-100 disabled:opacity-40"
        disabled={busy || disabled}
        onClick={() => void runShock({ ...DEMAND_BOOM_BODY, scenario: boomScenario })}
      >
        {boomButtonLabel(boomScenario)}
      </button>

      {/* ── Platform events ──────────────────────────────────── */}
      <p className={MCK_SECTION_TITLE}>Платформа</p>
      <button
        type="button"
        data-testid="trigger-promotion-btn"
        className={MCK_BUTTON_MD}
        disabled={busy || disabled}
        onClick={() => void runShock(MARKETPLACE_PROMOTION_BODY)}
      >
        Принудительная акция
      </button>
      <button
        type="button"
        data-testid="trigger-fee-cut-btn"
        className={MCK_BUTTON_MD}
        disabled={busy || disabled}
        onClick={() => void runShock(PLATFORM_FEE_CUT_BODY)}
      >
        Снижение комиссии
      </button>

      {message !== null ? <p className="text-xs text-emerald-700">{message}</p> : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
