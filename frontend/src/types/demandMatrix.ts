/** Demand matrix DTO (Spec 008 / Spec 009 §4.4). */

export type DemandMatrixCellDTO = {
  row: number;
  col: number;
  density: number;
};

export type DemandMatrixResponse = {
  run_id: string;
  tick_id: number;
  grid_size: number;
  cells: DemandMatrixCellDTO[];
};
