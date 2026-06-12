import type { MarketLeaderRowDTO } from "@/types/leaders";
import {
  algorithmAvatarClass,
  algorithmTypeLabel,
  formatCapital,
  logicStatusClass,
  logicStatusLabel,
  sellerRankAccent,
} from "@/utils/sellerDisplay";

type Props = {
  seller: MarketLeaderRowDTO;
  rank: number;
  maxCapital: number;
};

function formatRevenue(value: number): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

export function SellerRegistryCard({ seller, rank, maxCapital }: Props) {
  const accent = sellerRankAccent(Math.min(rank, 2));
  const capitalPct = maxCapital > 0 ? Math.min(100, (seller.working_capital / maxCapital) * 100) : 0;

  return (
    <article
      data-testid="seller-registry-card"
      data-seller-id={seller.seller_id}
      className={`flex items-start gap-3 border border-l-4 p-3 ${accent.stripeClass} border-border bg-white`}
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
        <span>{seller.algorithm_type}</span>
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

        <p className="mt-0.5 text-[10px] text-muted">
          Алгоритм: {algorithmTypeLabel(seller.algorithm_type)}
          {seller.is_bankrupt ? " · Банкрот" : " · Активен"}
        </p>

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
    </article>
  );
}
