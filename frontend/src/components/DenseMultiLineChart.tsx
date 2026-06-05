import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { ListingWideRow } from "@/state/types";

export const DENSE_LINE_COLORS = [
  "#1565c0",
  "#2e7d32",
  "#c62828",
  "#6a1b9a",
  "#ef6c00",
  "#00838f",
  "#ad1457",
  "#4527a0",
  "#558b2f",
  "#f9a825",
] as const;

type SeriesMeta = {
  dataKey: string;
  label: string;
};

type Props = {
  data: ListingWideRow[];
  series: SeriesMeta[];
  emptyMessage: string;
  yAxisLabel?: string;
};

export function DenseMultiLineChart({ data, series, emptyMessage, yAxisLabel }: Props) {
  const plottable = series.length > 0 && data.length > 0;

  if (!plottable) {
    return <p className="chart-empty">{emptyMessage}</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis dataKey="tick_id" tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} label={yAxisLabel ? { value: yAxisLabel, angle: -90, position: "insideLeft" } : undefined} />
        <Tooltip />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {series.map((s, idx) => (
          <Line
            key={s.dataKey}
            type="monotone"
            dataKey={s.dataKey}
            name={s.label}
            stroke={DENSE_LINE_COLORS[idx % DENSE_LINE_COLORS.length]}
            strokeWidth={1.5}
            isAnimationActive={false}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
