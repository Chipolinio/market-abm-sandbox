import { useDemandMatrix } from "@/hooks/useDemandMatrix";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";

function cellOpacity(density: number): number {
  return Math.max(0.05, density);
}

export function DemandMatrixGrid({ cells }: { cells: DemandMatrixCellDTO[] }) {
  return (
    <div data-testid="demand-matrix-grid" className="grid grid-cols-10 gap-0.5">
      {cells.map((cell) => (
        <div
          key={`${cell.row}-${cell.col}`}
          data-testid="demand-matrix-cell"
          title={`row=${cell.row} col=${cell.col} density=${cell.density}`}
          className="aspect-square rounded-sm bg-cyan-500"
          style={{ opacity: cellOpacity(cell.density) }}
        />
      ))}
    </div>
  );
}

export function DemandMatrixTab() {
  const { cells, loading, error } = useDemandMatrix(true);

  return (
    <div
      data-testid="demand-matrix-panel"
      className="rounded border border-slate-800 bg-slate-900/50 p-4"
    >
      <h2 className="mb-3 text-sm font-semibold text-slate-300">Demand Matrix</h2>
      {loading && cells.length === 0 ? (
        <p className="text-sm text-slate-400">Loading demand matrix…</p>
      ) : null}
      {error !== null ? <p className="text-sm text-red-400">{error}</p> : null}
      {cells.length > 0 ? <DemandMatrixGrid cells={cells} /> : null}
    </div>
  );
}
