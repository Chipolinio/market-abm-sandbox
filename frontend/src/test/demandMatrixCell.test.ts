import { describe, expect, it } from "vitest";

import {
  buildMatrixColorScale,
  cellBackgroundColor,
  cellStepIndex,
  DEMAND_MATRIX_COBALT_RGB,
  DEMAND_MATRIX_STEPS,
  normalizeMatrixDensity,
} from "@/utils/demandMatrixCell";

function parseRgb(color: string): [number, number, number] {
  const match = /^rgb\((\d+), (\d+), (\d+)\)$/.exec(color);
  expect(match).not.toBeNull();
  return [Number(match![1]), Number(match![2]), Number(match![3])];
}

describe("demandMatrixCell", () => {
  it("empty_cells_are_fully_transparent", () => {
    expect(cellBackgroundColor(0)).toBe("transparent");
    expect(cellBackgroundColor(-0.1)).toBe("transparent");
    expect(cellStepIndex(0, null)).toBe(-1);
  });

  it("single_active_cell_uses_peak_color", () => {
    const scale = buildMatrixColorScale([0, 0.11]);
    const [r, g, b] = DEMAND_MATRIX_COBALT_RGB;
    expect(cellBackgroundColor(0.11, scale)).toBe(`rgb(${r}, ${g}, ${b})`);
  });

  it("rank_scale_spreads_close_densities_across_steps", () => {
    const scale = buildMatrixColorScale([0.08, 0.09, 0.11, 0.15]);
    expect(normalizeMatrixDensity(0.08, scale)).toBe(0);
    expect(normalizeMatrixDensity(0.15, scale)).toBe(1);

    const low = cellBackgroundColor(0.08, scale);
    const high = cellBackgroundColor(0.15, scale);
    expect(low).not.toBe(high);
    expect(cellStepIndex(0.08, scale)).toBeLessThan(cellStepIndex(0.15, scale));
  });

  it("uses_five_discrete_palette_steps", () => {
    const colors = DEMAND_MATRIX_STEPS.map(([r, g, b]) => `rgb(${r}, ${g}, ${b})`);
    expect(new Set(colors).size).toBe(DEMAND_MATRIX_STEPS.length);

    const scale = buildMatrixColorScale([0.05, 0.1, 0.15, 0.2, 0.25]);
    const rendered = [0.05, 0.1, 0.15, 0.2, 0.25].map((density) =>
      cellBackgroundColor(density, scale),
    );
    expect(new Set(rendered).size).toBeGreaterThanOrEqual(4);
    expect(parseRgb(rendered[4]!)).toEqual([...DEMAND_MATRIX_COBALT_RGB]);
  });
});
