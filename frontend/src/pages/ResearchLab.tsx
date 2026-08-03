import type { ExperimentSummaryRow } from "@/types/experiments";

type Props = {
  experimentId: string;
  summaryRows: ExperimentSummaryRow[];
};

/** Spec 015 §10 — thin Research Lab viewer (reads precomputed summary only). */
export function ResearchLab({ experimentId, summaryRows }: Props) {
  return (
    <div className="min-h-screen bg-slate-50 p-6 text-slate-900">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Research Lab</h1>
        <p className="text-sm text-slate-600">
          Experiment <span className="font-mono">{experimentId}</span> — aggregate
          mean±CI from batch artifacts (no live simulation).
        </p>
      </header>
      <div className="overflow-x-auto rounded border border-slate-200 bg-white">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-slate-200 bg-slate-100 text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">metric</th>
              <th className="px-3 py-2">ml_share</th>
              <th className="px-3 py-2">window</th>
              <th className="px-3 py-2">mean</th>
              <th className="px-3 py-2">lo</th>
              <th className="px-3 py-2">hi</th>
            </tr>
          </thead>
          <tbody>
            {summaryRows.map((row) => (
              <tr
                key={`${row.metric}-${row.ml_share}-${row.window}`}
                className="border-b border-slate-100"
              >
                <td className="px-3 py-2 font-mono">{row.metric}</td>
                <td className="px-3 py-2">{row.ml_share}</td>
                <td className="px-3 py-2">{row.window}</td>
                <td className="px-3 py-2">{row.mean}</td>
                <td className="px-3 py-2">{row.lo}</td>
                <td className="px-3 py-2">{row.hi}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
