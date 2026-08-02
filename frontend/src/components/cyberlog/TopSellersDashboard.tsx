import { TopSellerCard } from "@/components/cyberlog/TopSellerCard";
import { useTopSellers } from "@/hooks/useTopSellers";

type Props = {
  asOfTick: number;
  pollLive?: boolean;
  highlightedSellerId: number | null;
  onHighlightSeller: (sellerId: number | null) => void;
};

export function TopSellersDashboard({
  asOfTick,
  pollLive = true,
  highlightedSellerId,
  onHighlightSeller,
}: Props) {
  const { sellers, loading, error } = useTopSellers(asOfTick, pollLive);
  const maxCapital = sellers.reduce((max, seller) => Math.max(max, seller.working_capital), 0);

  const handleSelect = (sellerId: number) => {
    onHighlightSeller(highlightedSellerId === sellerId ? null : sellerId);
  };

  return (
    <section
      data-testid="top-sellers-dashboard"
      className="flex h-[280px] shrink-0 flex-col gap-3 border-b border-border bg-matrix-substrate p-4"
    >
      <div className="flex items-center gap-2 border-l-4 border-accent pl-2">
        <h2 className="text-xs uppercase tracking-wider text-muted">Топ-3 селлера</h2>
        <span className="text-[10px] text-muted">по накопленной выручке</span>
      </div>

      {loading && sellers.length === 0 ? (
        <p className="text-xs text-muted">Загрузка…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {sellers.map((seller, index) => (
          <TopSellerCard
            key={seller.seller_id}
            seller={seller}
            rank={index}
            maxCapital={maxCapital}
            selected={highlightedSellerId === seller.seller_id}
            onSelect={handleSelect}
          />
        ))}
        {!loading && sellers.length === 0 && error === null ? (
          <p className="text-xs text-muted">Нет данных — запустите симуляцию</p>
        ) : null}
      </div>
    </section>
  );
}
