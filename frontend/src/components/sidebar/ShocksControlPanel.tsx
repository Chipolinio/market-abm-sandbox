import { useState } from "react";

import { ApiError } from "@/api/client";
import { triggerShock } from "@/api/simulation";

const DEMAND_CRASH_BODY = {
  shock_type: "demand_crash" as const,
  intensity: 1.0,
  duration_ticks: 10,
};

const MARKETPLACE_PROMOTION_BODY = {
  shock_type: "marketplace_promotion" as const,
  intensity: 1.0,
  duration_ticks: 15,
};

export function ShocksControlPanel() {
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const runShock = async (
    body: typeof DEMAND_CRASH_BODY | typeof MARKETPLACE_PROMOTION_BODY,
  ) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const response = await triggerShock(body);
      setMessage(`Shock queued (depth=${response.queue_depth})`);
    } catch (err) {
      const text =
        err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Shock failed";
      setError(text);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        disabled={busy}
        onClick={() => void runShock(DEMAND_CRASH_BODY)}
      >
        Запустить шок спроса
      </button>
      <button
        type="button"
        className="rounded border border-slate-700 bg-slate-800 px-3 py-2 text-sm hover:bg-slate-700 disabled:opacity-50"
        disabled={busy}
        onClick={() => void runShock(MARKETPLACE_PROMOTION_BODY)}
      >
        Принудительная акция маркетплейса
      </button>
      {message !== null ? <p className="text-xs text-green-400">{message}</p> : null}
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
    </div>
  );
}
