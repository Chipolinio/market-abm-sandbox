import { Fragment, useMemo } from "react";

import { useDemandMatrix } from "@/hooks/useDemandMatrix";
import type { DemandMatrixCellDTO } from "@/types/demandMatrix";
import {
  buildMatrixColorScale,
  cellBackgroundColor,
  cellLabelColor,
  cellStepIndex,
  DEMAND_MATRIX_STEPS,
  isEmptyMatrixCell,
} from "@/utils/demandMatrixCell";
import { pvdAxisLabel, strategyAxisLabel } from "@/utils/demandMatrixLabels";

type GridProps = {
  cells: DemandMatrixCellDTO[];
  rowCount: number;
  colCount: number;
  xLabels: string[];
  yLabels: string[];
};

export function DemandMatrixGrid({
  cells,
  rowCount,
  colCount,
  xLabels,
  yLabels,
}: GridProps) {
  const cellByKey = new Map(cells.map((cell) => [`${cell.row}-${cell.col}`, cell] as const));
  const colorScale = useMemo(
    () => buildMatrixColorScale(cells.map((cell) => cell.density)),
    [cells],
  );

  return (
    <div className="flex h-full min-h-0 w-full max-w-xl flex-col gap-2">
      <div
        className="grid flex-1 gap-2"
        style={{ gridTemplateColumns: `5.5rem repeat(${colCount}, minmax(0, 1fr))` }}
      >
        <div />
        {xLabels.map((label) => (
          <div
            key={`x-${label}`}
            className="flex items-end justify-center pb-1 text-center text-[10px] text-muted"
          >
            {strategyAxisLabel(label)}
          </div>
        ))}

        {yLabels.map((rowLabel, rowIdx) => (
          <Fragment key={`row-${rowLabel}`}>
            <div
              className="flex items-center justify-end pr-2 text-right text-[10px] text-muted"
            >
              {pvdAxisLabel(rowLabel)}
            </div>
            {Array.from({ length: colCount }, (_, colIdx) => {
              const cell = cellByKey.get(`${rowIdx}-${colIdx}`);
              const density = cell?.density ?? 0;
              const empty = isEmptyMatrixCell(density);
              const step = cellStepIndex(density, colorScale);
              const xLabel = xLabels[colIdx] ?? String(colIdx);
              return (
                <div
                  key={`cell-${rowIdx}-${colIdx}`}
                  data-testid="demand-matrix-cell"
                  data-density={density}
                  data-step={step}
                  title={`${pvdAxisLabel(rowLabel)} × ${strategyAxisLabel(xLabel)}: ${(density * 100).toFixed(0)}% сделок`}
                  className={`flex aspect-square min-h-10 items-center justify-center border bg-transparent ${
                    empty ? "border-[#F1F5F9]" : "border-border"
                  }`}
                  style={{
                    backgroundColor: empty ? "transparent" : cellBackgroundColor(density, colorScale),
                  }}
                >
                  {!empty ? (
                    <span
                      className="text-[11px] font-semibold tabular-nums leading-none"
                      style={{ color: cellLabelColor(step) }}
                    >
                      {(density * 100).toFixed(0)}%
                    </span>
                  ) : null}
                </div>
              );
            })}
          </Fragment>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted">
        <span>Доля сделок тика · цвет — относительно других ячеек матрицы</span>
        <div className="flex items-center gap-1" data-testid="demand-matrix-legend">
          {DEMAND_MATRIX_STEPS.map(([r, g, b], index) => (
            <span
              key={`legend-${index}`}
              className="inline-block h-2.5 w-5 border border-border"
              style={{ backgroundColor: `rgb(${r}, ${g}, ${b})` }}
              title={index === 0 ? "минимум" : index === DEMAND_MATRIX_STEPS.length - 1 ? "максимум" : undefined}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

type Props = {
  asOfTick: number;
  pollLive?: boolean;
};

export function DemandMatrixTab({ asOfTick, pollLive = false }: Props) {
  const { cells, rowCount, colCount, xLabels, yLabels, loading, error } = useDemandMatrix(
    true,
    asOfTick,
    pollLive,
  );

  return (
    <div data-testid="demand-matrix-panel" className="flex h-full min-h-0 flex-col bg-surface p-4">
      <h2 className="mb-3 shrink-0 text-xs uppercase tracking-wide text-muted">
        Карта эффективности · стратегия селлера × сегмент покупателя
      </h2>
      {loading && cells.length === 0 ? (
        <p className="text-xs text-muted">Загрузка матрицы…</p>
      ) : null}
      {error !== null ? <p className="text-xs text-red-600">{error}</p> : null}
      {cells.length > 0 ? (
        <div className="min-h-0 flex-1" data-testid="demand-matrix-grid">
          <DemandMatrixGrid
            cells={cells}
            rowCount={rowCount}
            colCount={colCount}
            xLabels={xLabels}
            yLabels={yLabels}
          />
        </div>
      ) : null}
    </div>
  );
}
