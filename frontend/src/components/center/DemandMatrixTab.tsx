import { useDemandMatrix } from "@/hooks/useDemandMatrix";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";
import { cellOpacity } from "@/utils/demandMatrixCell";

export function DemandMatrixGrid({ cells }: { cells: DemandMatrixCellDTO[] }) {
  return (
    <div
      data-testid="demand-matrix-grid"
      className="mx-auto grid h-full w-full max-w-2xl grid-cols-10 gap-0.5"
    >
      {cells.map((cell) => (
        <div
          key={`${cell.row}-${cell.col}`}
          data-testid="demand-matrix-cell"
          title={`строка=${cell.row} столбец=${cell.col} плотность=${cell.density}`}
          className="aspect-square rounded-sm bg-cyan-500"
          style={{ opacity: cellOpacity(cell.density) }}
        />
      ))}
    </div>
  );
}

type Props = {
  asOfTick: number;
  pollLive?: boolean;
};

export function DemandMatrixTab({ asOfTick, pollLive = false }: Props) {
  const { cells, loading, error } = useDemandMatrix(true, asOfTick, pollLive);

  return (
    <div
      data-testid="demand-matrix-panel"
      className="flex h-full min-h-0 flex-col rounded border border-slate-800 bg-slate-900/60 p-4"
    >
      <h2 className="mb-3 shrink-0 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Матрица спроса (10×10) · рейтинг × цена
      </h2>
      {loading && cells.length === 0 ? (
        <p className="text-xs text-slate-500">Загрузка матрицы…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-400">{error}</p> : null}
      {cells.length > 0 ? (
        <div className="min-h-0 flex-1">
          <DemandMatrixGrid cells={cells} />
        </div>
      ) : null}
    </div>
  );
}
