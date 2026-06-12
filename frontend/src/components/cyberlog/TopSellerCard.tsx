import type { MarketLeaderRowDTO } from "@/types/leaders";
import {
  algorithmAvatarClass,
  formatCapital,
  logicStatusClass,
  logicStatusLabel,
  sellerRankAccent,
} from "@/utils/sellerDisplay";

type Props = {
  seller: MarketLeaderRowDTO;
  rank: number;
  maxCapital: number;
  selected: boolean;
  onSelect: (sellerId: number) => void;
};

export function TopSellerCard({ seller, rank, maxCapital, selected, onSelect }: Props) {
  const accent = sellerRankAccent(rank);
  const capitalPct = maxCapital > 0 ? Math.min(100, (seller.working_capital / maxCapital) * 100) : 0;

  return (
    <button
      type="button"
      data-testid="top-seller-card"
      aria-pressed={selected}
      onClick={() => onSelect(seller.seller_id)}
      className={`flex w-full items-start gap-3 border border-l-4 p-2.5 text-left transition-colors ${accent.stripeClass} ${
        selected
          ? "border-accent/40 bg-slate-50 ring-1 ring-accent/20"
          : "border-border bg-white hover:bg-slate-50"
      }`}
    >
      <span
        data-testid="seller-rank-badge"
        className={`flex h-6 w-6 shrink-0 items-center justify-center text-[11px] font-medium ${accent.badgeClass}`}
      >
        {rank + 1}
      </span>

      <span
        data-testid="seller-algorithm-avatar"
        className={`flex h-9 w-9 shrink-0 items-center justify-center text-[10px] font-medium ring-1 ${algorithmAvatarClass(seller.algorithm_type)}`}
      >
        {seller.algorithm_type}
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs text-foreground">
            Селлер #{seller.seller_id}
          </span>
          <span
            data-testid="seller-logic-status"
            className={`shrink-0 border px-1.5 py-0.5 text-[10px] ${logicStatusClass(seller.logic_status)}`}
          >
            {logicStatusLabel(seller.logic_status)}
          </span>
        </div>

        <div className="mt-1.5 grid grid-cols-2 gap-x-2 text-[10px] text-muted">
          <span>
            Баланс:{" "}
            <span className="font-mono text-foreground">{formatCapital(seller.working_capital)}</span>
          </span>
          <span>
            Склад:{" "}
            <span className="font-mono text-foreground">{seller.inventory_stock}</span>
          </span>
        </div>

        <div
          data-testid="seller-capital-bar"
          className="mt-1.5 h-1 w-full bg-slate-100"
          aria-hidden
        >
          <div className={`h-full ${accent.barClass}`} style={{ width: `${capitalPct}%` }} />
        </div>
      </div>
    </button>
  );
}
