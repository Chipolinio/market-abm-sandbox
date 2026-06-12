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
import { MCK_SERIES_COLORS } from "@/styles/chartPalette";

export const DENSE_LINE_COLORS = MCK_SERIES_COLORS;

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
        <CartesianGrid horizontal vertical={false} stroke="#F1F5F9" />
        <XAxis
          dataKey="tick_id"
          tick={{ fontSize: 10, fill: "#64748B" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#64748B" }}
          axisLine={false}
          tickLine={false}
          label={
            yAxisLabel
              ? { value: yAxisLabel, angle: -90, position: "insideLeft", fill: "#64748B", fontSize: 10 }
              : undefined
          }
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "transparent",
            border: "none",
            boxShadow: "none",
            color: "#475569",
            fontSize: 11,
            padding: 0,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10, color: "#64748B" }} />
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
