import { useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { configureSession } from "@/api/simulation";

type Props = {
  disabled: boolean;
};

const DEFAULT_N_BUYERS = 10_000;
const DEFAULT_CATBOOST_PCT = 40;
const DEFAULT_RULE_BASED_PCT = 35;

function pctToRatio(value: number): number {
  return Math.round(value) / 100;
}

export function EnvironmentConfigurator({ disabled }: Props) {
  const [nBuyers, setNBuyers] = useState(DEFAULT_N_BUYERS);
  const [catboostPct, setCatboostPct] = useState(DEFAULT_CATBOOST_PCT);
  const [ruleBasedPct, setRuleBasedPct] = useState(DEFAULT_RULE_BASED_PCT);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const basicPct = Math.max(0, 100 - catboostPct - ruleBasedPct);
  const mixSum = catboostPct + ruleBasedPct + basicPct;
  const mixValid = Math.abs(mixSum - 100) <= 1;

  const sellerMix = useMemo(
    () => ({
      catboost_pct: pctToRatio(catboostPct),
      rule_based_pct: pctToRatio(ruleBasedPct),
      basic_pct: pctToRatio(basicPct),
    }),
    [basicPct, catboostPct, ruleBasedPct],
  );

  const applyDisabled = disabled || busy || !mixValid;

  const onApply = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await configureSession({ n_buyers: nBuyers, seller_mix: sellerMix });
      setMessage("Configuration saved");
    } catch (err) {
      const text =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Configure failed";
      setError(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs text-slate-400">
        Buyer sample size: {nBuyers.toLocaleString()}
        <input
          type="range"
          role="slider"
          data-testid="n-buyers-slider"
          min={1_000}
          max={100_000}
          step={1_000}
          value={nBuyers}
          disabled={disabled}
          onChange={(e) => setNBuyers(Number(e.target.value))}
          className="w-full"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-400">
        CatBoost mix: {catboostPct}%
        <input
          type="range"
          role="slider"
          data-testid="catboost-slider"
          min={0}
          max={100}
          step={1}
          value={catboostPct}
          disabled={disabled}
          onChange={(e) => setCatboostPct(Number(e.target.value))}
          className="w-full"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-slate-400">
        Rule-based mix: {ruleBasedPct}%
        <input
          type="range"
          role="slider"
          data-testid="rule-based-slider"
          min={0}
          max={100}
          step={1}
          value={ruleBasedPct}
          disabled={disabled}
          onChange={(e) => setRuleBasedPct(Number(e.target.value))}
          className="w-full"
        />
      </label>

      <p className="text-xs text-slate-500">Basic mix: {basicPct}% (auto)</p>

      {!mixValid ? (
        <p className="text-xs text-red-400">Seller mix must sum to 100% (±1%)</p>
      ) : null}

      <button
        type="button"
        className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        disabled={applyDisabled}
        onClick={() => void onApply()}
      >
        Применить
      </button>

      {message !== null ? <p className="text-xs text-green-400">{message}</p> : null}
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
