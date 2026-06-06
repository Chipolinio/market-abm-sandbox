/** Minimum tile opacity for zero-density cells (Spec 009 §4.7). */
export const DEMAND_MATRIX_MIN_OPACITY = 0.05;

export function cellOpacity(density: number): number {
  return Math.max(DEMAND_MATRIX_MIN_OPACITY, density);
}
