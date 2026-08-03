import type { MarketLeaderRowDTO } from "@/types/leaders";
import { RankingScoreBreakdown } from "@/components/center/RankingScoreBreakdown";
import {
  algorithmAvatarGlyph,
  algorithmAvatarClass,
  algorithmTypeLabel,
  formatCapital,
  logicStatusClass,
  logicStatusLabel,
  sellerHealthBadgeClass,
  sellerHealthCardClass,
  sellerHealthLabel,
  sellerHealthStatus,
  sellerRankAccent,
} from "@/utils/sellerDisplay";

type Props = {
  seller: MarketLeaderRowDTO;
  rank: number;
  maxCapital: number;
  selected?: boolean;
  onSelect?: (sellerId: number | null) => void;
  asOfTick?: number;
};

function formatRevenue(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

export function SellerRegistryCard({
  seller,
  rank,
  maxCapital,
  selected = false,
  onSelect,
  asOfTick = 0,
}: Props) {
  const accent = sellerRankAccent(Math.min(rank, 2));
  const capitalPct = maxCapital > 0 ? Math.min(100, (seller.working_capital / maxCapital) * 100) : 0;
  const health = sellerHealthStatus(seller, maxCapital);

  return (
    <div
      data-testid="seller-registry-card"
      data-seller-id={seller.seller_id}
      className={`relative border border-l-4 ${accent.stripeClass} ${sellerHealthCardClass(health)} ${
        selected ? "border-accent ring-1 ring-accent/25" : "border-border"
      }`}
    >
      <button
        type="button"
        aria-pressed={selected}
        onClick={() => onSelect?.(selected ? null : seller.seller_id)}
        className="flex w-full items-start gap-3 p-3 text-left"
      >
        <span
          data-testid="seller-rank-badge"
          className={`flex h-7 w-7 shrink-0 items-center justify-center text-xs font-medium ${accent.badgeClass}`}
        >
          {rank + 1}
        </span>

        <span
          data-testid="seller-algorithm-avatar"
          title={algorithmTypeLabel(seller.algorithm_type)}
          className={`flex h-10 w-10 shrink-0 flex-col items-center justify-center text-[9px] font-medium leading-tight ring-1 ${algorithmAvatarClass(seller.algorithm_type)}`}
        >
          <span>{algorithmAvatarGlyph(seller.algorithm_type)}</span>
          <span className="text-[8px]">{seller.algorithm_type}</span>
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm text-foreground">Селлер #{seller.seller_id}</h3>
            <span
              data-testid="seller-logic-status"
              className={`shrink-0 border px-1.5 py-0.5 text-[10px] ${logicStatusClass(seller.logic_status)}`}
            >
              {logicStatusLabel(seller.logic_status)}
            </span>
          </div>

          <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-[10px] text-muted">
            <span>Алгоритм: {algorithmTypeLabel(seller.algorithm_type)}</span>
            <span
              className={`border px-1.5 py-0.5 ${sellerHealthBadgeClass(health)}`}
              data-testid="seller-health-status"
            >
              {sellerHealthLabel(health)}
            </span>
          </div>

          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] sm:grid-cols-4">
            <div>
              <dt className="text-muted">Капитал</dt>
              <dd className="font-mono text-foreground">{formatCapital(seller.working_capital)}</dd>
            </div>
            <div>
              <dt className="text-muted">Склад</dt>
              <dd className="font-mono text-foreground">{seller.inventory_stock}</dd>
            </div>
            <div>
              <dt className="text-muted">Выручка за тик</dt>
              <dd className="font-mono text-foreground">{formatRevenue(seller.tick_revenue)}</dd>
            </div>
            <div>
              <dt className="text-muted">Накопленная</dt>
              <dd className="font-mono text-foreground">{formatRevenue(seller.cumulative_revenue)}</dd>
            </div>
          </dl>

          <div
            data-testid="seller-capital-bar"
            className="mt-2 h-1 w-full bg-slate-100"
            aria-hidden
          >
            <div className={`h-full ${accent.barClass}`} style={{ width: `${capitalPct}%` }} />
          </div>
        </div>
        {seller.is_bankrupt ? (
          <span className="absolute right-3 top-3 rotate-[-8deg] border border-slate-400 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-slate-600">
            Bankrupt
          </span>
        ) : null}
      </button>
      {selected ? (
        <div className="px-3 pb-3">
          <RankingScoreBreakdown
            sellerId={seller.seller_id}
            tickId={asOfTick}
            enabled
          />
        </div>
      ) : null}
    </div>
  );
}
