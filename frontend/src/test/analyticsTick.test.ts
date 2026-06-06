import { describe, expect, it } from "vitest";

import { toLastCompletedTick } from "@/utils/analyticsTick";

describe("toLastCompletedTick", () => {
  it("returns_zero_for_idle_counter", () => {
    expect(toLastCompletedTick(0)).toBe(0);
  });

  it("returns_previous_tick_for_running_counter", () => {
    expect(toLastCompletedTick(1)).toBe(0);
    expect(toLastCompletedTick(42)).toBe(41);
  });
});
