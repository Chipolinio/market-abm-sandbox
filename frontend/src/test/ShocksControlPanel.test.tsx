// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShocksControlPanel } from "@/components/sidebar/ShocksControlPanel";

const triggerShock = vi.fn();

vi.mock("@/api/simulation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/simulation")>();
  return {
    ...actual,
    triggerShock: (...args: unknown[]) => triggerShock(...args),
  };
});

afterEach(() => {
  cleanup();
  triggerShock.mockReset();
});

describe("ShocksControlPanel", () => {
  it("posts_demand_crash_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Запустить — Шок спроса" }));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "demand_crash",
      intensity: 1.0,
      scenario: "standard",
    });
  });

  it("posts_severe_scenario_when_selected", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "severe" } });
    fireEvent.click(screen.getByRole("button", { name: "Запустить — Рецессия" }));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledWith({
        shock_type: "demand_crash",
        intensity: 1.0,
        scenario: "severe",
      });
    });
  });

  it("updates_button_label_when_scenario_changes", () => {
    render(<ShocksControlPanel />);

    expect(screen.getByRole("button", { name: "Запустить — Шок спроса" })).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "mild" } });
    expect(screen.getByRole("button", { name: "Запустить — Слабый спад" })).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "severe" } });
    expect(screen.getByRole("button", { name: "Запустить — Рецессия" })).toBeTruthy();
  });

  it("posts_marketplace_promotion_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "marketplace_promotion",
      queue_depth: 2,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(
      screen.getByRole("button", { name: "Принудительная акция маркетплейса" }),
    );

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "marketplace_promotion",
      intensity: 1.0,
      duration_ticks: 15,
    });
  });

  it("shows_queue_depth_message_on_success", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 3,
    });

    render(<ShocksControlPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Запустить — Шок спроса" }));

    await waitFor(() => {
      expect(screen.getByText(/Shock queued \(depth=3\)/)).toBeTruthy();
    });
  });

  it("disables_all_controls_when_runtime_not_started", () => {
    render(<ShocksControlPanel disabled />);

    expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "Запустить — Шок спроса" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(screen.getByText("Шоки доступны только после запуска симуляции.")).toBeTruthy();
  });
});
