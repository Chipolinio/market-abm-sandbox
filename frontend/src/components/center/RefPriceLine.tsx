import { ReferenceLine } from "recharts";

export type RefPriceLineProps = {
  refPrice: number | null | undefined;
};

/**
 * Horizontal p50_hist anchor on price chart (Spec 014 §5.2).
 * Returns null when ref_price is missing (cold-start).
 */
export function RefPriceLine({ refPrice }: RefPriceLineProps) {
  if (refPrice === null || refPrice === undefined || Number.isNaN(refPrice)) {
    return null;
  }

  return (
    <ReferenceLine
      y={refPrice}
      stroke="#64748B"
      strokeDasharray="6 4"
      strokeWidth={1.5}
      ifOverflow="extendDomain"
      label={{
        value: "p50_hist",
        position: "insideTopRight",
        fill: "#64748B",
        fontSize: 10,
      }}
    />
  );
}
