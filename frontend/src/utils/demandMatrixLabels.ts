const STRATEGY_LABELS: Record<string, string> = {
  MaxProfit: "CatBoost",
  MaxVolume: "MaxVolume",
  RatingMaximizer: "RatingMax",
};

const PVD_LABELS: Record<string, string> = {
  rich: "Лояльные к качеству",
  standard: "Стандарт",
  low: "Чувств. к цене",
};

export function strategyAxisLabel(key: string): string {
  return STRATEGY_LABELS[key] ?? key;
}

export function pvdAxisLabel(key: string): string {
  return PVD_LABELS[key] ?? key;
}
