// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ControlPanel, isConfigurableWorkerState } from "@/components/ControlPanel";

afterEach(() => {
  cleanup();
});

describe("isConfigurableWorkerState", () => {
  it.each(["IDLE", "STOPPED"] as const)("returns_true_for_%s", (state) => {
    expect(isConfigurableWorkerState(state)).toBe(true);
  });

  it.each(["RUNNING", "PAUSED", "FAILED"] as const)("returns_false_for_%s", (state) => {
    expect(isConfigurableWorkerState(state)).toBe(false);
  });
});

describe("ControlPanel", () => {
  const onActionComplete = vi.fn(async (_before: string, _action: string) => undefined);

  it("renders_three_sections", () => {
    render(<ControlPanel workerState="IDLE" onActionComplete={onActionComplete} />);

    expect(screen.getByTestId("control-panel-environment")).toBeTruthy();
    expect(screen.getByTestId("control-panel-shocks")).toBeTruthy();
    expect(screen.getByTestId("control-panel-simulation")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Запустить шок спроса" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Старт" })).toBeTruthy();
  });

  it("disables_environment_when_running", () => {
    render(<ControlPanel workerState="RUNNING" onActionComplete={onActionComplete} />);

    const sliders = screen.getAllByRole("slider");
    for (const slider of sliders) {
      expect((slider as HTMLInputElement).disabled).toBe(true);
    }

    const applyButton = screen.getByRole("button", { name: "Применить" }) as HTMLButtonElement;
    expect(applyButton.disabled).toBe(true);
  });

  it("disables_environment_when_paused", () => {
    render(<ControlPanel workerState="PAUSED" onActionComplete={onActionComplete} />);

    const applyButton = screen.getByRole("button", { name: "Применить" }) as HTMLButtonElement;
    expect(applyButton.disabled).toBe(true);
  });

  it("disables_start_when_running", () => {
    render(<ControlPanel workerState="RUNNING" onActionComplete={onActionComplete} />);

    const start = screen.getByRole("button", { name: "Старт" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });

  it("enables_pause_when_running", () => {
    render(<ControlPanel workerState="RUNNING" onActionComplete={onActionComplete} />);

    const pause = screen.getByRole("button", { name: "Пауза" }) as HTMLButtonElement;
    expect(pause.disabled).toBe(false);
  });

  it("disables_start_when_failed", () => {
    render(<ControlPanel workerState="FAILED" onActionComplete={onActionComplete} />);

    const start = screen.getByRole("button", { name: "Старт" }) as HTMLButtonElement;
    expect(start.disabled).toBe(true);
  });
});
