/** Spec 014 §5.3 — structured DEMAND_SHOCK causal fields (never parse message). */

export type DemandShockCausal = {
  impulse: number;
  stress_after: number;
  est_half_life_ticks: number;
  scenario?: string;
  shock_type?: string;
};

function asFiniteNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

/**
 * Build causal DTO from event/marker payload only.
 * `message` is ignored (Spec 014 §5.3 — no regex on free text).
 */
export function extractDemandShockCausal(
  payload: Record<string, unknown> | null | undefined,
  _message?: string,
): DemandShockCausal | null {
  if (payload === null || payload === undefined) {
    return null;
  }
  const impulse = asFiniteNumber(payload.impulse);
  const stressAfter =
    asFiniteNumber(payload.stress_after) ?? asFiniteNumber(payload.stress);
  const halfLife = asFiniteNumber(payload.est_half_life_ticks);
  if (impulse === null || stressAfter === null || halfLife === null) {
    return null;
  }
  const scenario =
    typeof payload.scenario === "string" ? payload.scenario : undefined;
  const shockType =
    typeof payload.shock_type === "string" ? payload.shock_type : undefined;
  return {
    impulse,
    stress_after: stressAfter,
    est_half_life_ticks: halfLife,
    scenario,
    shock_type: shockType,
  };
}
