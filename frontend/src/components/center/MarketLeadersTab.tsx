import { useMarketLeaders } from "@/hooks/useMarketLeaders";
import type { MarketLeaderRowDTO } from "@/types/leaders";

function formatMoney(value: number): string {
  return value.toFixed(2);
}

function statusLabel(isBankrupt: boolean): string {
  return isBankrupt ? "БАНКРОТ" : "АКТИВЕН";
}

export function MarketLeadersTable({ leaders }: { leaders: MarketLeaderRowDTO[] }) {
  return (
    <table className="w-full border-collapse text-xs">
      <thead className="sticky top-0 bg-surface">
        <tr className="border-b border-border text-left text-muted">
          <th className="px-2 py-1.5">Место</th>
          <th className="px-2 py-1.5">ID селлера</th>
          <th className="px-2 py-1.5">Капитал</th>
          <th className="px-2 py-1.5">Выручка за тик</th>
          <th className="px-2 py-1.5">Накопленная</th>
          <th className="px-2 py-1.5">Статус</th>
        </tr>
      </thead>
      <tbody>
        {leaders.map((leader, index) => (
          <tr key={leader.seller_id} className="border-b border-border hover:bg-slate-50">
            <td className="px-2 py-1.5 text-muted">{index + 1}</td>
            <td className="px-2 py-1.5" data-testid="leader-seller-id">
              {leader.seller_id}
            </td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.working_capital)}</td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.tick_revenue)}</td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.cumulative_revenue)}</td>
            <td className="px-2 py-1.5">
              <span className={leader.is_bankrupt ? "text-red-600" : "text-emerald-700"}>
                {statusLabel(leader.is_bankrupt)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type Props = {
  asOfTick: number;
};

export function MarketLeadersTab({ asOfTick }: Props) {
  const { leaders, loading, error } = useMarketLeaders(true, asOfTick);

  return (
    <div
      data-testid="market-leaders-panel"
      className="h-full bg-white p-4"
    >
      <h2 className="mb-3 text-xs uppercase tracking-wide text-muted">
        Лидеры рынка
      </h2>
      {loading && leaders.length === 0 ? (
        <p className="text-xs text-muted">Загрузка лидеров…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
      {leaders.length > 0 ? <MarketLeadersTable leaders={leaders} /> : null}
      {!loading && leaders.length === 0 && error === null ? (
        <p className="text-xs text-muted">Нет данных — запустите симуляцию</p>
      ) : null}
    </div>
  );
}
