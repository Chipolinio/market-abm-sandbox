// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlPanel } from "@/components/ControlPanel";

afterEach(() => {
  cleanup();
});

describe("ControlPanel", () => {
  it("disables_start_when_running", () => {
    render(
      <ControlPanel state="RUNNING" totalGmv={1200} onActionComplete={vi.fn(async (_before: string) => undefined)} />,
    );

    const start = screen.getByRole("button", { name: "Start" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });

  it("enables_pause_when_running", () => {
    render(
      <ControlPanel state="RUNNING" totalGmv={1200} onActionComplete={vi.fn(async (_before: string) => undefined)} />,
    );

    const pause = screen.getByRole("button", { name: "Pause" }) as HTMLButtonElement;
    expect(pause.disabled).toBe(false);
  });

  it("disables_start_when_failed", () => {
    render(
      <ControlPanel state="FAILED" totalGmv={0} onActionComplete={vi.fn(async (_before: string) => undefined)} />,
    );

    const start = screen.getByRole("button", { name: "Start" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });
});
