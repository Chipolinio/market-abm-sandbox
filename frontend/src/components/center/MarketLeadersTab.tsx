import { useMarketLeaders } from "@/hooks/useMarketLeaders";
import type { MarketLeaderRowDTO } from "@/types/leaders";

function formatMoney(value: number): string {
  return value.toFixed(2);
}

function statusLabel(isBankrupt: boolean): string {
  return isBankrupt ? "BANKRUPT" : "ACTIVE";
}

export function MarketLeadersTable({ leaders }: { leaders: MarketLeaderRowDTO[] }) {
  return (
    <table className="w-full border-collapse text-sm">
      <thead>
        <tr className="border-b border-slate-700 text-left text-slate-400">
          <th className="px-2 py-2">Rank</th>
          <th className="px-2 py-2">Seller ID</th>
          <th className="px-2 py-2">Working Capital</th>
          <th className="px-2 py-2">Tick Revenue</th>
          <th className="px-2 py-2">Cumulative</th>
          <th className="px-2 py-2">Status</th>
        </tr>
      </thead>
      <tbody>
        {leaders.map((leader, index) => (
          <tr key={leader.seller_id} className="border-b border-slate-800">
            <td className="px-2 py-2">{index + 1}</td>
            <td className="px-2 py-2" data-testid="leader-seller-id">
              {leader.seller_id}
            </td>
            <td className="px-2 py-2">{formatMoney(leader.working_capital)}</td>
            <td className="px-2 py-2">{formatMoney(leader.tick_revenue)}</td>
            <td className="px-2 py-2">{formatMoney(leader.cumulative_revenue)}</td>
            <td className="px-2 py-2">
              <span
                className={
                  leader.is_bankrupt ? "text-red-400" : "text-green-400"
                }
              >
                {statusLabel(leader.is_bankrupt)}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function MarketLeadersTab() {
  const { leaders, loading, error } = useMarketLeaders(true);

  return (
    <div data-testid="market-leaders-panel" className="rounded border border-slate-800 bg-slate-900/50 p-4">
      <h2 className="mb-3 text-sm font-semibold text-slate-300">Market Leaders</h2>
      {loading && leaders.length === 0 ? (
        <p className="text-sm text-slate-400">Loading leaders…</p>
      ) : null}
      {error !== null ? <p className="text-sm text-red-400">{error}</p> : null}
      {leaders.length > 0 ? <MarketLeadersTable leaders={leaders} /> : null}
    </div>
  );
}
