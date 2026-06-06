import type { MarketLeaderRowDTO } from "@/types/leaders";
import {
  algorithmAvatarClass,
  formatCapital,
  logicStatusClass,
  logicStatusLabel,
} from "@/utils/sellerDisplay";

type Props = {
  seller: MarketLeaderRowDTO;
  selected: boolean;
  onSelect: (sellerId: number) => void;
};

export function TopSellerCard({ seller, selected, onSelect }: Props) {
  return (
    <button
      type="button"
      data-testid="top-seller-card"
      aria-pressed={selected}
      onClick={() => onSelect(seller.seller_id)}
      className={`flex w-full items-start gap-3 rounded border p-2 text-left transition-colors ${
        selected
          ? "border-cyan-500 bg-cyan-950/30 ring-1 ring-cyan-600"
          : "border-zinc-800 bg-zinc-950/60 hover:border-zinc-600"
      }`}
    >
      <span
        data-testid="seller-algorithm-avatar"
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[10px] font-bold ring-1 ${algorithmAvatarClass(seller.algorithm_type)}`}
      >
        {seller.algorithm_type}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs font-medium text-zinc-200">
            Селлер #{seller.seller_id}
          </span>
          <span
            data-testid="seller-logic-status"
            className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] ${logicStatusClass(seller.logic_status)}`}
          >
            {logicStatusLabel(seller.logic_status)}
          </span>
        </div>
        <div className="mt-1 grid grid-cols-2 gap-x-2 text-[10px] text-zinc-400">
          <span>
            Баланс:{" "}
            <span className="font-mono text-zinc-200">{formatCapital(seller.working_capital)}</span>
          </span>
          <span>
            Склад:{" "}
            <span className="font-mono text-zinc-200">{seller.inventory_stock}</span>
          </span>
        </div>
      </div>
    </button>
  );
}
