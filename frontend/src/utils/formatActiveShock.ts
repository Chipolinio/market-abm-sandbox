import type { ActiveShockDTO } from "@/types/macro";
import { shockScenarioLabel } from "@/utils/uiLabels";

/** Format one active shock line for Zone A (Spec 014 §4.4). */
export function formatActiveShockLine(shock: ActiveShockDTO): string {
  const token = shock.shock_type.toUpperCase();
  const scenarioRu = shockScenarioLabel(shock.scenario);
  const scenarioPart = scenarioRu ? ` ${scenarioRu}` : "";
  if (shock.remaining_ticks === null) {
    return `${token}${scenarioPart} · режим`;
  }
  return `${token}${scenarioPart} · ${shock.remaining_ticks} тиков`;
}
