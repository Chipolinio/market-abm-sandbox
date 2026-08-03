import type { MacroRegime } from "@/types/macro";

export type MacroRegimeBadgeProps = {
  regime: MacroRegime | null;
  stale?: boolean;
};

function regimeClass(regime: MacroRegime): string {
  switch (regime) {
    case "stress":
      return "border-red-600 bg-red-50 text-red-700";
    case "recovery":
      return "border-amber-600 bg-amber-50 text-amber-800";
    case "expansion":
      return "border-emerald-600 bg-emerald-50 text-emerald-800";
    case "normal":
    default:
      return "border-slate-400 bg-slate-50 text-slate-600";
  }
}

/** Zone B colored regime pill (Spec 014 §4.2). */
export function MacroRegimeBadge({ regime, stale = false }: MacroRegimeBadgeProps) {
  if (regime === null) {
    return null;
  }

  return (
    <span
      data-testid="macro-regime-badge"
      className={`rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${regimeClass(regime)}${
        stale ? " opacity-70 outline outline-1 outline-dashed outline-slate-400" : ""
      }`}
    >
      {regime.toUpperCase()}
    </span>
  );
}
