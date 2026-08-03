import { describe, expect, it } from "vitest";

import { markerLabelForShock, mergeEventMarker } from "@/utils/eventMarkers";

describe("mergeEventMarker", () => {
  it("replaces_exact_label_and_tick", () => {
    const prev = [{ tickId: 10, label: "ШОК", payload: null }];
    const next = mergeEventMarker(prev, {
      tickId: 10,
      label: "ШОК",
      payload: { impulse: 0.5 },
    });
    expect(next).toHaveLength(1);
    expect(next[0]?.payload).toEqual({ impulse: 0.5 });
  });

  it("ws_confirmed_drops_optimistic_any_tick_distance", () => {
    const prev = [{ tickId: 39, label: "ШОК", payload: null }];
    const next = mergeEventMarker(prev, {
      tickId: 42,
      label: "ШОК",
      payload: { impulse: 0.4, stress_after: 0.5 },
    });
    expect(next).toHaveLength(1);
    expect(next[0]?.tickId).toBe(42);
    expect(next[0]?.payload).toMatchObject({ impulse: 0.4 });
  });

  it("optimistic_replaces_previous_optimistic_same_label", () => {
    const prev = [{ tickId: 10, label: "АКЦИЯ", payload: null }];
    const next = mergeEventMarker(prev, {
      tickId: 15,
      label: "АКЦИЯ",
      payload: null,
    });
    expect(next).toHaveLength(1);
    expect(next[0]?.tickId).toBe(15);
  });

  it("keeps_distinct_labels_on_same_tick", () => {
    const prev = [{ tickId: 10, label: "ШОК", payload: { impulse: 1 } }];
    const next = mergeEventMarker(prev, {
      tickId: 10,
      label: "АКЦИЯ",
      payload: null,
    });
    expect(next).toHaveLength(2);
  });
});

describe("markerLabelForShock", () => {
  it("maps_promo_only_optimistic_path", () => {
    expect(markerLabelForShock("demand_crash")).toBeNull();
    expect(markerLabelForShock("marketplace_promotion")).toBe("АКЦИЯ");
    expect(markerLabelForShock("platform_fee_hike")).toBeNull();
  });
});
