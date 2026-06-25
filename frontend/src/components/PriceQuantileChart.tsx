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
import { MCK_CHART } from "@/styles/chartPalette";

export const EMPTY_PRICE_MESSAGE = "Ожидание данных симуляции…";

const AXIS_TICK = { fontSize: 10, fill: "#64748B" };
const QUANTILE_STROKE = "#94A3B8";
const BAND_FILL = "rgba(241, 245, 249, 0.5)";

type Props = {
  data: PriceChartRow[];
  highlightedSellerSeries?: {
    sellerId: number;
    points: Array<{ tick_id: number; price: number | null }>;
  } | null;
};

function warnIfQuantileOrderBroken(row: PriceChartRow): void {
  if (row.p10 === null || row.p50 === null || row.p90 === null) {
    return;
  }
  if (row.p10 > row.p50 || row.p50 > row.p90) {
    console.warn(`Quantile order violated at tick ${row.tick_id}`, row);
  }
}

export function PriceQuantileChart({ data, highlightedSellerSeries = null }: Props) {
  if (data.length === 0 || !hasPlottablePriceData(data)) {
    return (
      <p className="flex h-full items-center justify-center text-xs italic text-muted">
        {EMPTY_PRICE_MESSAGE}
      </p>
    );
  }

  data.forEach(warnIfQuantileOrderBroken);
  const highlightedPointByTick = new Map(
    (highlightedSellerSeries?.points ?? []).map((point) => [point.tick_id, point.price] as const),
  );
  const chartData = data.map((row) => ({
    ...row,
    highlightedSellerPrice: highlightedPointByTick.get(row.tick_id) ?? null,
  }));

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
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
          domain={["auto", "auto"]}
          label={{
            value: "Цена",
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
        />
        <Legend wrapperStyle={{ fontSize: 10, color: "#64748B" }} />
        <Area
          type="monotone"
          dataKey="p90"
          stackId="band"
          stroke="none"
          fill={BAND_FILL}
          fillOpacity={1}
          isAnimationActive={false}
          dot={false}
          legendType="none"
        />
        <Area
          type="monotone"
          dataKey="p10"
          stackId="band"
          stroke="none"
          fill="#FFFFFF"
          fillOpacity={1}
          isAnimationActive={false}
          dot={false}
          legendType="none"
        />
        <Line
          type="monotone"
          dataKey="p50"
          stroke={MCK_CHART.navy}
          strokeWidth={2.5}
          isAnimationActive={false}
          dot={false}
          name="P50 (Медиана)"
        />
        <Line
          type="monotone"
          dataKey="p10"
          stroke={QUANTILE_STROKE}
          strokeWidth={1}
          isAnimationActive={false}
          dot={false}
          name="P10 (Мин)"
        />
        <Line
          type="monotone"
          dataKey="p90"
          stroke={QUANTILE_STROKE}
          strokeWidth={1}
          isAnimationActive={false}
          dot={false}
          name="P90 (Макс)"
        />
        {highlightedSellerSeries !== null ? (
          <Line
            type="monotone"
            dataKey="highlightedSellerPrice"
            stroke="#2563EB"
            strokeWidth={2}
            strokeDasharray="5 4"
            isAnimationActive={false}
            dot={false}
            connectNulls
            name={`Seller #${highlightedSellerSeries.sellerId} price`}
          />
        ) : null}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
