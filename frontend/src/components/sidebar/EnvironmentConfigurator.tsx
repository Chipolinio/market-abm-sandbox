import { useEffect, useMemo, useState } from "react";

import { ApiError } from "@/api/client";
import { configureSession, fetchSessionConfigure } from "@/api/simulation";
import type { SessionConfigureRequest } from "@/types/session";
import {
  DEFAULT_SESSION_CONFIG,
  readSessionConfig,
  writeSessionConfig,
} from "@/utils/sessionConfigStorage";

type Props = {
  disabled: boolean;
};

function pctToRatio(value: number): number {
  return Math.round(value) / 100;
}

function ratioToPct(value: number): number {
  return Math.round(value * 100);
}

function applyConfigToState(
  config: SessionConfigureRequest,
  setters: {
    setNBuyers: (value: number) => void;
    setNSellers: (value: number) => void;
    setCatboostPct: (value: number) => void;
    setRuleBasedPct: (value: number) => void;
  },
): void {
  setters.setNBuyers(config.n_buyers);
  setters.setNSellers(config.n_sellers ?? DEFAULT_SESSION_CONFIG.n_sellers);
  setters.setCatboostPct(ratioToPct(config.seller_mix.catboost_pct));
  setters.setRuleBasedPct(ratioToPct(config.seller_mix.rule_based_pct));
}

export function EnvironmentConfigurator({ disabled }: Props) {
  const [nBuyers, setNBuyers] = useState(DEFAULT_SESSION_CONFIG.n_buyers);
  const [nSellers, setNSellers] = useState(DEFAULT_SESSION_CONFIG.n_sellers);
  const [catboostPct, setCatboostPct] = useState(40);
  const [ruleBasedPct, setRuleBasedPct] = useState(35);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      const cached = readSessionConfig();
      if (cached !== null) {
        applyConfigToState(cached, { setNBuyers, setNSellers, setCatboostPct, setRuleBasedPct });
      }

      try {
        const remote = await fetchSessionConfigure();
        if (cancelled) {
          return;
        }
        applyConfigToState(remote, { setNBuyers, setNSellers, setCatboostPct, setRuleBasedPct });
        writeSessionConfig(remote);
      } catch {
        // keep cached / defaults
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, []);

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
    const body: SessionConfigureRequest = { n_buyers: nBuyers, n_sellers: nSellers, seller_mix: sellerMix };
    try {
      await configureSession(body);
      writeSessionConfig(body);
      setMessage("Конфигурация сохранена");
    } catch (err) {
      const text =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Не удалось применить конфигурацию";
      setError(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-xs text-muted">
        Число покупателей: {nBuyers.toLocaleString("ru-RU")}
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

      <label className="flex flex-col gap-1 text-xs text-muted">
        Число селлеров: {nSellers.toLocaleString("ru-RU")}
        <input
          type="range"
          role="slider"
          data-testid="n-sellers-slider"
          min={5}
          max={500}
          step={5}
          value={nSellers}
          disabled={disabled}
          onChange={(e) => setNSellers(Number(e.target.value))}
          className="w-full"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs text-muted">
        Доля CatBoost: {catboostPct}%
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

      <label className="flex flex-col gap-1 text-xs text-muted">
        Доля rule-based: {ruleBasedPct}%
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

      <p className="text-xs text-muted">Доля basic: {basicPct}% (авто)</p>

      {!mixValid ? (
        <p className="text-xs text-red-600">Сумма долей селлеров должна быть 100% (±1%)</p>
      ) : null}

      <button
        type="button"
        className="border border-border bg-white px-3 py-2 text-sm text-accent hover:bg-slate-50 disabled:opacity-50"
        disabled={applyDisabled}
        onClick={() => void onApply()}
      >
        Применить
      </button>

      {message !== null ? <p className="text-xs text-emerald-700">{message}</p> : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
