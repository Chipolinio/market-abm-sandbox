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
  if (data.length === 0 || !hasPlottableGmvData(data)) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-slate-500">
        Waiting for GMV data…
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
        />
        <YAxis tick={{ fontSize: 10, fill: "#94a3b8" }} stroke="#475569" />
        <Tooltip
          contentStyle={{
            backgroundColor: "#0f172a",
            border: "1px solid #334155",
            fontSize: 11,
          }}
          formatter={(value: number, name: string) => {
            if (name === "gmv") {
              return [value.toFixed(2), "GMV"];
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
