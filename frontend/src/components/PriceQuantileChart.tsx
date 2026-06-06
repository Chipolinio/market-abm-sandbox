import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hasPlottablePriceData } from "@/state/chartSeries";
import type { PriceChartRow } from "@/state/types";

export const EMPTY_PRICE_MESSAGE = "Ожидание данных симуляции…";

type Props = {
  data: PriceChartRow[];
};

function warnIfQuantileOrderBroken(row: PriceChartRow): void {
  if (row.p10 === null || row.p50 === null || row.p90 === null) {
    return;
  }
  if (row.p10 > row.p50 || row.p50 > row.p90) {
    console.warn(`Quantile order violated at tick ${row.tick_id}`, row);
  }
}

export function PriceQuantileChart({ data }: Props) {
  if (data.length === 0 || !hasPlottablePriceData(data)) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-slate-500">
        {EMPTY_PRICE_MESSAGE}
      </p>
    );
  }

  data.forEach(warnIfQuantileOrderBroken);

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
        <XAxis
          dataKey="tick_id"
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          stroke="#475569"
          label={{ value: "Тик", position: "insideBottom", offset: -2, fill: "#94a3b8", fontSize: 10 }}
        />
        <YAxis
          tick={{ fontSize: 10, fill: "#94a3b8" }}
          stroke="#475569"
          domain={["auto", "auto"]}
          label={{ value: "Цена", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 10 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#0f172a",
            border: "1px solid #334155",
            fontSize: 11,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 10 }} />
        <Area
          type="monotone"
          dataKey="p90"
          stackId="band"
          stroke="none"
          fill="#0ea5e9"
          fillOpacity={0.25}
          isAnimationActive={false}
          dot={false}
          name="p90 (90%)"
        />
        <Area
          type="monotone"
          dataKey="p10"
          stackId="band"
          stroke="none"
          fill="#0f172a"
          fillOpacity={1}
          isAnimationActive={false}
          dot={false}
          name="p10 маска"
        />
        <Line
          type="monotone"
          dataKey="p50"
          stroke="#38bdf8"
          strokeWidth={2}
          isAnimationActive={false}
          dot={false}
          name="p50 (медиана)"
        />
        <Line
          type="monotone"
          dataKey="p10"
          stroke="#64748b"
          strokeDasharray="4 4"
          isAnimationActive={false}
          dot={false}
          name="p10"
        />
        <Line
          type="monotone"
          dataKey="p90"
          stroke="#64748b"
          strokeDasharray="4 4"
          isAnimationActive={false}
          dot={false}
          name="p90"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
