/** Demand matrix DTO — strategy_type × pvd_segment transaction heatmap. */

export type DemandMatrixCellDTO = {
  row: number;
  col: number;
  density: number;
};

export type DemandMatrixResponse = {
  run_id: string;
  tick_id: number;
  grid_size: number;
  row_count: number;
  col_count: number;
  x_labels: string[];
  y_labels: string[];
  axis_x: string;
  axis_y: string;
  cells: DemandMatrixCellDTO[];
};
