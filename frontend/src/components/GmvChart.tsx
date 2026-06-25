import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Label,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { hasPlottableGmvData } from "@/state/chartSeries";
import type { GmvTickPoint } from "@/state/types";
import { MCK_CHART } from "@/styles/chartPalette";
import type { EventMarker } from "@/components/center/types";
const AXIS_TICK = { fontSize: 10, fill: "#64748B" };

type Props = {
  data: GmvTickPoint[];
  eventMarkers?: EventMarker[];
};

export function GmvChart({ data, eventMarkers = [] }: Props) {
  if (data.length === 0) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-muted">
        Ожидание данных GMV…
      </p>
    );
  }

  if (!hasPlottableGmvData(data)) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-muted">
        Нет оборота за выбранный период (тики: {data[data.length - 1]?.tick_id ?? 0})…
      </p>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid horizontal vertical={false} stroke="#F1F5F9" />
        <XAxis
          dataKey="tick_id"
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          label={{
            value: "Тик",
            position: "insideBottom",
            offset: -2,
            fill: "#64748B",
            fontSize: 10,
          }}
        />
        <YAxis
          tick={AXIS_TICK}
          axisLine={false}
          tickLine={false}
          label={{
            value: "GMV",
            angle: -90,
            position: "insideLeft",
            fill: "#64748B",
            fontSize: 10,
          }}
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
          formatter={(value: number, name: string) => {
            if (name === "gmv") {
              return [value.toFixed(2), "Оборот"];
            }
            return [value, name];
          }}
        />
        <Bar
          dataKey="gmv"
          fill={MCK_CHART.teal}
          fillOpacity={0.9}
          isAnimationActive={false}
          name="gmv"
        />
        {eventMarkers.map((marker) => (
          <ReferenceLine
            key={`${marker.label}-${marker.tickId}`}
            x={marker.tickId}
            stroke="#B91C1C"
            strokeDasharray="4 4"
            isFront
          >
            <Label value={marker.label} position="top" fill="#B91C1C" fontSize={10} />
          </ReferenceLine>
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
