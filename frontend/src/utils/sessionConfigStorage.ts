import type { SessionConfigureRequest } from "@/types/session";

export const SESSION_CONFIG_STORAGE_KEY = "market_abm_session_config";

export const DEFAULT_SESSION_CONFIG: SessionConfigureRequest = {
  n_buyers: 10_000,
  n_sellers: 50,
  seller_mix: {
    catboost_pct: 0.4,
    rule_based_pct: 0.35,
    basic_pct: 0.25,
  },
};

export function readSessionConfig(): SessionConfigureRequest | null {
  try {
    const raw = localStorage.getItem(SESSION_CONFIG_STORAGE_KEY);
    if (raw === null) {
      return null;
    }
    return JSON.parse(raw) as SessionConfigureRequest;
  } catch {
    return null;
  }
}

export function writeSessionConfig(config: SessionConfigureRequest): void {
  try {
    localStorage.setItem(SESSION_CONFIG_STORAGE_KEY, JSON.stringify(config));
  } catch {
    // ignore quota / private mode
  }
}

export function resolveSessionConfig(): SessionConfigureRequest {
  return { ...DEFAULT_SESSION_CONFIG, ...readSessionConfig() };
}
