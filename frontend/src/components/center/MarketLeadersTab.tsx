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
    <table className="w-full border-collapse text-xs">
      <thead className="sticky top-0 bg-slate-900">
        <tr className="border-b border-slate-700 text-left text-slate-500">
          <th className="px-2 py-1.5">Rank</th>
          <th className="px-2 py-1.5">Seller ID</th>
          <th className="px-2 py-1.5">Working Capital</th>
          <th className="px-2 py-1.5">Tick Revenue</th>
          <th className="px-2 py-1.5">Cumulative</th>
          <th className="px-2 py-1.5">Status</th>
        </tr>
      </thead>
      <tbody>
        {leaders.map((leader, index) => (
          <tr key={leader.seller_id} className="border-b border-slate-800 hover:bg-slate-800/40">
            <td className="px-2 py-1.5 text-slate-400">{index + 1}</td>
            <td className="px-2 py-1.5" data-testid="leader-seller-id">
              {leader.seller_id}
            </td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.working_capital)}</td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.tick_revenue)}</td>
            <td className="px-2 py-1.5 font-mono">{formatMoney(leader.cumulative_revenue)}</td>
            <td className="px-2 py-1.5">
              <span className={leader.is_bankrupt ? "text-red-400" : "text-emerald-400"}>
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
      className="h-full rounded border border-slate-800 bg-slate-900/60 p-4"
    >
      <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Market Leaders
      </h2>
      {loading && leaders.length === 0 ? (
        <p className="text-xs text-slate-500">Loading leaders…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
      {leaders.length > 0 ? <MarketLeadersTable leaders={leaders} /> : null}
    </div>
  );
}
