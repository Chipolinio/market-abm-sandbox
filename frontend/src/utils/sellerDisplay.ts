import type { LogicStatus, MarketLeaderRowDTO } from "@/types/leaders";

export function logicStatusLabel(status: LogicStatus): string {
  switch (status) {
    case "roi_optimization":
      return "Оптимизация ROI";
    case "aggressive_dumping":
      return "Агрессивный демпинг";
    case "bankrupt":
      return "Банкрот";
    default:
      return "Rule-based";
  }
}

export function logicStatusClass(status: LogicStatus): string {
  switch (status) {
    case "roi_optimization":
      return "text-emerald-800 border-emerald-200 bg-emerald-50";
    case "aggressive_dumping":
      return "text-red-700 border-red-200 bg-red-50";
    case "bankrupt":
      return "text-slate-600 border-slate-200 bg-slate-100";
    default:
      return "text-blue-900 border-blue-200 bg-blue-50";
  }
}

export function algorithmAvatarClass(algorithm: MarketLeaderRowDTO["algorithm_type"]): string {
  switch (algorithm) {
    case "CB":
      return "bg-violet-100 text-violet-800 ring-violet-200";
    case "REPR":
      return "bg-teal-100 text-teal-800 ring-teal-200";
    default:
      return "bg-blue-100 text-blue-900 ring-blue-200";
  }
}

export function algorithmAvatarGlyph(algorithm: MarketLeaderRowDTO["algorithm_type"]): string {
  switch (algorithm) {
    case "CB":
      return "AI";
    case "REPR":
      return "GEAR";
    default:
      return "RULE";
  }
}

/** Rank stripe + badge for top-3 leaderboard (0 = gold tier). */
export function sellerRankAccent(rank: number): {
  stripeClass: string;
  badgeClass: string;
  barClass: string;
} {
  switch (rank) {
    case 0:
      return {
        stripeClass: "border-l-[#051C2C]",
        badgeClass: "bg-[#051C2C] text-white",
        barClass: "bg-[#051C2C]",
      };
    case 1:
      return {
        stripeClass: "border-l-[#0D9488]",
        badgeClass: "bg-[#0D9488] text-white",
        barClass: "bg-[#0D9488]",
      };
    default:
      return {
        stripeClass: "border-l-[#1E40AF]",
        badgeClass: "bg-[#1E40AF] text-white",
        barClass: "bg-[#1E40AF]",
      };
  }
}

export function algorithmTypeLabel(algorithm: MarketLeaderRowDTO["algorithm_type"]): string {
  switch (algorithm) {
    case "CB":
      return "CatBoost";
    case "REPR":
      return "Repricing";
    default:
      return "Rule-based";
  }
}

export function formatCapital(value: number): string {
  if (value >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(1)}k`;
  }
  return value.toFixed(0);
}

export type SellerHealth = "healthy" | "fragile" | "critical" | "bankrupt";

export function sellerHealthStatus(
  seller: Pick<MarketLeaderRowDTO, "is_bankrupt" | "working_capital" | "inventory_stock">,
  maxCapital: number,
): SellerHealth {
  if (seller.is_bankrupt) {
    return "bankrupt";
  }
  const capitalRatio = maxCapital > 0 ? seller.working_capital / maxCapital : 0;
  if (capitalRatio <= 0.2 || (seller.inventory_stock > 0 && seller.working_capital <= seller.inventory_stock * 10)) {
    return "critical";
  }
  if (capitalRatio <= 0.45) {
    return "fragile";
  }
  return "healthy";
}

export function sellerHealthLabel(health: SellerHealth): string {
  switch (health) {
    case "healthy":
      return "Здоровье: устойчив";
    case "fragile":
      return "Здоровье: хрупкий";
    case "critical":
      return "Здоровье: тревога";
    default:
      return "Здоровье: банкрот";
  }
}

export function sellerHealthCardClass(health: SellerHealth): string {
  switch (health) {
    case "healthy":
      return "";
    case "fragile":
      return "bg-amber-50/40";
    case "critical":
      return "border-orange-300 bg-orange-50";
    default:
      return "border-slate-300 bg-slate-100 grayscale";
  }
}

export function sellerHealthBadgeClass(health: SellerHealth): string {
  switch (health) {
    case "healthy":
      return "border-emerald-200 bg-emerald-50 text-emerald-800";
    case "fragile":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "critical":
      return "border-orange-200 bg-orange-50 text-orange-800";
    default:
      return "border-slate-300 bg-slate-200 text-slate-700";
  }
}
