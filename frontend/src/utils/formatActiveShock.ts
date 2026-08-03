import type { ActiveShockDTO } from "@/types/macro";

/** Format one active shock line for Zone A (Spec 014 §4.4). */
export function formatActiveShockLine(shock: ActiveShockDTO): string {
  const token = shock.shock_type.toUpperCase();
  const scenarioPart = shock.scenario ? ` ${shock.scenario}` : "";
  if (shock.remaining_ticks === null) {
    return `${token}${scenarioPart} · regime`;
  }
  return `${token}${scenarioPart} · ${shock.remaining_ticks} ticks left`;
}
