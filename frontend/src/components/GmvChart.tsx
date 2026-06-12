import {
  Bar,
  CartesianGrid,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hasPlottableGmvData } from "@/state/chartSeries";
import type { GmvTickPoint } from "@/state/types";

type Props = {
  data: GmvTickPoint[];
};

export function GmvChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-slate-500">
        Ожидание данных GMV…
      </p>
    );
  }

  if (!hasPlottableGmvData(data)) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-slate-500">
        Нет оборота за выбранный период (тики: {data[data.length - 1]?.tick_id ?? 0})…
      </p>
    );
  }

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
          label={{ value: "GMV", angle: -90, position: "insideLeft", fill: "#94a3b8", fontSize: 10 }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: "#0f172a",
            border: "1px solid #334155",
            fontSize: 11,
          }}
          formatter={(value: number, name: string) => {
            if (name === "gmv") {
              return [value.toFixed(2), "Оборот"];
            }
            return [value, name];
          }}
        />
        <Bar
          dataKey="gmv"
          fill="#22d3ee"
          fillOpacity={0.85}
          isAnimationActive={false}
          name="gmv"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
