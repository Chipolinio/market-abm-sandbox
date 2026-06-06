import { describe, expect, it } from "vitest";

import { formatCompactGmv } from "@/utils/formatCompactGmv";

describe("formatCompactGmv", () => {
  it.each([
    [500, "500"],
    [1_200, "1.2k"],
    [3_400_000, "3.4M"],
    [0, "0"],
  ] as const)("formatCompactGmv(%i) -> %s", (value, expected) => {
    expect(formatCompactGmv(value)).toBe(expected);
  });
});
