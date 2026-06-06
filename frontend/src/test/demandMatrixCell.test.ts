import { describe, expect, it } from "vitest";

import { cellOpacity, DEMAND_MATRIX_MIN_OPACITY } from "@/utils/demandMatrixCell";

describe("demandMatrixCell", () => {
  it("clamps_zero_density_to_min_opacity", () => {
    expect(cellOpacity(0)).toBe(DEMAND_MATRIX_MIN_OPACITY);
    expect(cellOpacity(0.02)).toBe(DEMAND_MATRIX_MIN_OPACITY);
  });

  it("uses_density_when_above_min", () => {
    expect(cellOpacity(0.5)).toBe(0.5);
    expect(cellOpacity(1)).toBe(1);
  });
});
