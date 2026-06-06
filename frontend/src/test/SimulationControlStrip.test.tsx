// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SimulationControlStrip } from "@/components/sidebar/SimulationControlStrip";

afterEach(() => {
  cleanup();
});

const noopComplete = vi.fn(async (_before: string) => undefined);

describe("SimulationControlStrip", () => {
  it("disables_start_when_running", () => {
    render(<SimulationControlStrip state="RUNNING" onActionComplete={noopComplete} />);

    const start = screen.getByRole("button", { name: "Start" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });

  it("enables_pause_when_running", () => {
    render(<SimulationControlStrip state="RUNNING" onActionComplete={noopComplete} />);

    const pause = screen.getByRole("button", { name: "Pause" }) as HTMLButtonElement;
    expect(pause.disabled).toBe(false);
  });

  it("disables_step_unless_paused", () => {
    render(<SimulationControlStrip state="RUNNING" onActionComplete={noopComplete} />);
    expect((screen.getByRole("button", { name: "Step" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    cleanup();
    render(<SimulationControlStrip state="PAUSED" onActionComplete={noopComplete} />);
    expect((screen.getByRole("button", { name: "Step" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });

  it("disables_reset_when_running", () => {
    render(<SimulationControlStrip state="RUNNING" onActionComplete={noopComplete} />);

    const reset = screen.getByRole("button", { name: "Reset" }) as HTMLButtonElement;
    expect(reset.disabled).toBe(true);
  });

  it("enables_start_when_idle", () => {
    render(<SimulationControlStrip state="IDLE" onActionComplete={noopComplete} />);

    const start = screen.getByRole("button", { name: "Start" }) as HTMLButtonElement;
    expect(start.disabled).toBe(false);
  });
});
