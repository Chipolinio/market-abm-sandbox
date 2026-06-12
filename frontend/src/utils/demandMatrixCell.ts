/** Cobalt #1E40AF — peak step. */
export const DEMAND_MATRIX_COBALT_RGB = [30, 64, 175] as const;

/** Five discrete fills: pale → cobalt; gaps are large enough to read at a glance. */
export const DEMAND_MATRIX_STEPS: readonly (readonly [number, number, number])[] = [
  [239, 246, 255], // blue-50
  [191, 219, 254], // blue-200
  [96, 165, 250], // blue-400
  [37, 99, 235], // blue-600
  DEMAND_MATRIX_COBALT_RGB,
] as const;

export type MatrixColorScale = {
  /** Sorted unique positive densities in the current matrix. */
  levels: readonly number[];
};

export function buildMatrixColorScale(densities: readonly number[]): MatrixColorScale | null {
  const levels = [...new Set(densities.filter((d) => d > 0))].sort((a, b) => a - b);
  if (levels.length === 0) {
    return null;
  }
  return { levels };
}

/** Rank within the matrix so close absolute values still spread across the palette. */
export function normalizeMatrixDensity(density: number, scale: MatrixColorScale | null): number {
  if (density <= 0 || scale === null) {
    return 0;
  }
  const { levels } = scale;
  if (levels.length === 1) {
    return 1;
  }
  const idx = levels.indexOf(density);
  if (idx < 0) {
    return 0;
  }
  return idx / (levels.length - 1);
}

export function cellStepIndex(density: number, scale: MatrixColorScale | null): number {
  if (density <= 0) {
    return -1;
  }
  const normalized = normalizeMatrixDensity(density, scale);
  const stepCount = DEMAND_MATRIX_STEPS.length;
  if (normalized >= 1) {
    return stepCount - 1;
  }
  return Math.min(stepCount - 1, Math.floor(normalized * stepCount));
}

export function cellBackgroundColor(
  density: number,
  scale: MatrixColorScale | null = null,
): string {
  const step = cellStepIndex(density, scale);
  if (step < 0) {
    return "transparent";
  }
  const [r, g, b] = DEMAND_MATRIX_STEPS[step]!;
  return `rgb(${r}, ${g}, ${b})`;
}

export function cellLabelColor(step: number): string {
  return step >= 2 ? "#FFFFFF" : "#051C2C";
}

export function isEmptyMatrixCell(density: number): boolean {
  return density <= 0;
}
