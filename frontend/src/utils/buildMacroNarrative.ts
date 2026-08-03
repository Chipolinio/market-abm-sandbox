import type { ActiveShockDTO, MacroRegime, MacroStateDTO } from "@/types/macro";

export type MacroNarrative = {
  title: string;
  detail: string;
};

export type BuildMacroNarrativeOptions = {
  paused?: boolean;
};

const REGIME_TITLE: Record<MacroRegime, (macro: MacroStateDTO) => string> = {
  normal: () => "Рынок в норме",
  stress: (macro) => `Стресс спроса · episode #${macro.episode_id}`,
  recovery: (macro) => {
    const eta =
      macro.est_recovery_eta_ticks === null ? "—" : `~${macro.est_recovery_eta_ticks}`;
    return `Восстановление после стресса · ETA ${eta}`;
  },
  expansion: (macro) => `Экспансия спроса · episode #${macro.episode_id}`,
};

function topShockDetail(shocks: ActiveShockDTO[]): string {
  if (shocks.length === 0) {
    return "Активных шоков нет";
  }
  const top = [...shocks].sort((a, b) => b.intensity - a.intensity)[0];
  const token = top.shock_type.toUpperCase();
  const scenario = top.scenario ?? "n/a";
  if (top.remaining_ticks === null) {
    return `${token} ${scenario} · regime`;
  }
  return `${token} ${scenario} · ${top.remaining_ticks} ticks left`;
}

/**
 * Rule-based narrative from WS macro + shocks (Spec 014 §5.1). No LLM.
 */
export function buildMacroNarrative(
  macro: MacroStateDTO | null,
  shocks: ActiveShockDTO[],
  options: BuildMacroNarrativeOptions = {},
): MacroNarrative {
  if (macro === null) {
    const title = options.paused ? "[Пауза] Нет macro_state" : "Нет macro_state";
    return { title, detail: "Ожидание данных симуляции" };
  }

  let title = REGIME_TITLE[macro.regime](macro);
  if (options.paused) {
    title = `[Пауза] ${title}`;
  }

  let detail = topShockDetail(shocks);
  if (shocks.length === 0 && macro.stress > 0) {
    detail = "Scar/churn активны; импульс уже поглощён режимом";
  }

  return { title, detail };
}
