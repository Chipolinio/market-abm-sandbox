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
      return "text-emerald-400 border-emerald-800 bg-emerald-950/40";
    case "aggressive_dumping":
      return "text-red-400 border-red-800 bg-red-950/40";
    case "bankrupt":
      return "text-zinc-500 border-zinc-700 bg-zinc-900/60";
    default:
      return "text-cyan-400 border-cyan-800 bg-cyan-950/40";
  }
}

export function algorithmAvatarClass(algorithm: MarketLeaderRowDTO["algorithm_type"]): string {
  switch (algorithm) {
    case "CB":
      return "bg-violet-900 text-violet-200 ring-violet-700";
    case "REPR":
      return "bg-orange-900 text-orange-200 ring-orange-700";
    default:
      return "bg-sky-900 text-sky-200 ring-sky-700";
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
