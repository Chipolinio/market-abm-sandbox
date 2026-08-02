import { SELLERS_REGISTRY_LIMIT } from "@/api/analytics";
import { SellerRegistryCard } from "@/components/center/SellerRegistryCard";
import { useMarketLeaders } from "@/hooks/useMarketLeaders";

type Props = {
  asOfTick: number;
  highlightedSellerId?: number | null;
  onHighlightSeller?: (sellerId: number | null) => void;
};

export function MarketLeadersTab({
  asOfTick,
  highlightedSellerId = null,
  onHighlightSeller,
}: Props) {
  const { leaders, loading, error } = useMarketLeaders(true, asOfTick, SELLERS_REGISTRY_LIMIT);
  const maxCapital = leaders.reduce((max, seller) => Math.max(max, seller.working_capital), 0);

  return (
    <div
      data-testid="market-leaders-panel"
      className="flex h-full min-h-0 flex-col bg-white p-4"
    >
      <h2 className="mb-1 shrink-0 text-xs uppercase tracking-wide text-muted">Реестр селлеров</h2>
      <p className="mb-3 shrink-0 text-[10px] text-muted">Сортировка: накопленная выручка</p>

      {loading && leaders.length === 0 ? (
        <p className="text-xs text-muted">Загрузка реестра…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}

      {leaders.length > 0 ? (
        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
          {leaders.map((seller, index) => (
            <SellerRegistryCard
              key={seller.seller_id}
              seller={seller}
              rank={index}
              maxCapital={maxCapital}
              selected={highlightedSellerId === seller.seller_id}
              onSelect={onHighlightSeller}
            />
          ))}
        </div>
      ) : null}

      {!loading && leaders.length === 0 && error === null ? (
        <p className="text-xs text-muted">Нет данных — запустите симуляцию</p>
      ) : null}
    </div>
  );
}
