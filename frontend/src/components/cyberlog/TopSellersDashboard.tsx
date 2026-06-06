import { TopSellerCard } from "@/components/cyberlog/TopSellerCard";
import { useTopSellers } from "@/hooks/useTopSellers";

type Props = {
  asOfTick: number;
  highlightedSellerId: number | null;
  onHighlightSeller: (sellerId: number | null) => void;
};

export function TopSellersDashboard({
  asOfTick,
  highlightedSellerId,
  onHighlightSeller,
}: Props) {
  const { sellers, loading, error } = useTopSellers(asOfTick);

  const handleSelect = (sellerId: number) => {
    onHighlightSeller(highlightedSellerId === sellerId ? null : sellerId);
  };

  return (
    <section
      data-testid="top-sellers-dashboard"
      className="flex h-[280px] shrink-0 flex-col gap-2 border-b border-zinc-800 p-4"
    >
      <h2 className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Топ-3 селлера
      </h2>
      {loading && sellers.length === 0 ? (
        <p className="text-xs text-zinc-600">Загрузка…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto">
        {sellers.map((seller) => (
          <TopSellerCard
            key={seller.seller_id}
            seller={seller}
            selected={highlightedSellerId === seller.seller_id}
            onSelect={handleSelect}
          />
        ))}
        {!loading && sellers.length === 0 && error === null ? (
          <p className="text-xs text-zinc-600">Нет данных — запустите симуляцию</p>
        ) : null}
      </div>
    </section>
  );
}
