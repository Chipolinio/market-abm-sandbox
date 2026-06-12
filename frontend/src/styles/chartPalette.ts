/** McKinsey-inspired chart palette: deep navy anchor + distinct consulting accents. */
export const MCK_CHART = {
  navy: "#051C2C",
  teal: "#0D9488",
  cobalt: "#1E40AF",
  wine: "#BE123C",
  amber: "#B45309",
  emerald: "#047857",
  violet: "#5B21B6",
  sky: "#0369A1",
} as const;

export const MCK_SERIES_COLORS = [
  MCK_CHART.navy,
  MCK_CHART.teal,
  MCK_CHART.cobalt,
  MCK_CHART.wine,
  MCK_CHART.amber,
  MCK_CHART.emerald,
  MCK_CHART.violet,
  MCK_CHART.sky,
  "#0E7490",
  "#7C2D12",
] as const;
