// @vitest-environment jsdom
import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { usePriceIndexDelta } from "@/hooks/usePriceIndexDelta";

afterEach(() => {
  cleanup();
});

describe("usePriceIndexDelta", () => {
  it("returns_zero_on_first_value", () => {
    const { result, rerender } = renderHook(
      ({ index }: { index: number | undefined }) => usePriceIndexDelta(index),
      { initialProps: { index: 1.0 as number | undefined } },
    );

    expect(result.current).toBe(0);

    rerender({ index: 1.05 });
    expect(result.current).toBeCloseTo(0.05);

    rerender({ index: 1.0 });
    expect(result.current).toBeCloseTo(-0.05);
  });
});
