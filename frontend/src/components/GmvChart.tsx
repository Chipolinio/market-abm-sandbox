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
    return <p className="chart-empty">Waiting for GMV data…</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
        <XAxis dataKey="tick_id" tick={{ fontSize: 12 }} />
        <YAxis tick={{ fontSize: 12 }} />
        <Tooltip
          formatter={(value: number, name: string) => {
            if (name === "gmv") {
              return [value.toFixed(2), "GMV"];
            }
            return [value, name];
          }}
        />
        <Bar
          dataKey="gmv"
          fill="#66bb6a"
          isAnimationActive={false}
          name="gmv"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
