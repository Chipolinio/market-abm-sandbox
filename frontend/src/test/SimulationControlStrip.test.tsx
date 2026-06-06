// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SimulationControlStrip } from "@/components/sidebar/SimulationControlStrip";

afterEach(() => {
  cleanup();
});

describe("SimulationControlStrip", () => {
  it("disables_start_when_running", () => {
    render(
      <SimulationControlStrip
        state="RUNNING"
        onActionComplete={vi.fn(async (_before: string) => undefined)}
      />,
    );

    const start = screen.getByRole("button", { name: "Start" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });

  it("enables_pause_when_running", () => {
    render(
      <SimulationControlStrip
        state="RUNNING"
        onActionComplete={vi.fn(async (_before: string) => undefined)}
      />,
    );

    const pause = screen.getByRole("button", { name: "Pause" }) as HTMLButtonElement;
    expect(pause.disabled).toBe(false);
  });
});
