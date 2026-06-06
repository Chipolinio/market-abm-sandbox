import { useEffect, useRef, useState } from "react";

/** UI-only scalar delta for ZONE B price index trend arrow (Spec 009 §2.5). */
export function usePriceIndexDelta(marketPriceIndex: number | undefined): number {
  const prevRef = useRef<number | null>(null);
  const [delta, setDelta] = useState(0);

  useEffect(() => {
    if (marketPriceIndex === undefined) {
      return;
    }
    const prev = prevRef.current;
    if (prev !== null) {
      setDelta(marketPriceIndex - prev);
    }
    prevRef.current = marketPriceIndex;
  }, [marketPriceIndex]);

  return delta;
}
