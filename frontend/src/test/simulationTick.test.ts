import { describe, expect, it } from "vitest";

import { resolveSimulationTick } from "@/utils/simulationTick";

describe("resolveSimulationTick", () => {
  it("prefers_status_over_stale_ws_zero", () => {
    const tick = resolveSimulationTick(
      { run_id: "r", state: "PAUSED", current_tick: 330, elapsed_time_seconds: 0, last_error: null },
      {
        tick_id: 0,
        timestamp_utc: "",
        market_summary: {
          mean_price: 0,
          total_gmv: 0,
          total_transactions: 0,
          price_quantiles: null,
        },
        active_drift_alerts: [],
        worker_state: "PAUSED",
      },
    );
    expect(tick).toBe(330);
  });

  it("uses_ws_when_ahead_of_status", () => {
    const tick = resolveSimulationTick(
      { run_id: "r", state: "RUNNING", current_tick: 10, elapsed_time_seconds: 0, last_error: null },
      {
        tick_id: 12,
        timestamp_utc: "",
        market_summary: {
          mean_price: 0,
          total_gmv: 0,
          total_transactions: 0,
          price_quantiles: null,
        },
        ticker_metrics: { current_tick: 12 } as never,
        active_drift_alerts: [],
        worker_state: "RUNNING",
      },
    );
    expect(tick).toBe(12);
  });
});
