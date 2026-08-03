import type { MacroRegime } from "@/types/macro";

/** Display labels for macro regime pill (UI Russian). */
export function macroRegimeLabel(regime: MacroRegime): string {
  switch (regime) {
    case "normal":
      return "В норме";
    case "stress":
      return "Стресс";
    case "recovery":
      return "Восстановление";
    case "expansion":
      return "Экспансия";
    default:
      return regime;
  }
}

/** Seller strategy_type → RU label. */
export function strategyTypeLabel(strategyType: string): string {
  switch (strategyType) {
    case "MaxProfit":
      return "Макс. прибыль";
    case "MaxVolume":
      return "Макс. объём";
    case "RatingMaximizer":
      return "Макс. рейтинг";
    default:
      return strategyType;
  }
}

/** Buyer PVD segment → RU label. */
export function segmentLabel(segment: string): string {
  switch (segment) {
    case "rich":
      return "Богатые";
    case "standard":
      return "Средние";
    case "low":
      return "Эконом";
    default:
      return segment;
  }
}

const SCENARIO_RU: Record<string, string> = {
  mild: "слабый",
  standard: "стандарт",
  severe: "сильный",
};

export function shockScenarioLabel(scenario: string | null | undefined): string | null {
  if (scenario == null || scenario === "") {
    return null;
  }
  return SCENARIO_RU[scenario] ?? scenario;
}
