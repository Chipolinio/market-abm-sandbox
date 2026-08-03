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
  // ── Demand crash ─────────────────────────────────────────────────────────

  it("posts_demand_crash_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(screen.getByTestId("trigger-crash-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "demand_crash",
      intensity: 1.0,
      scenario: "standard",
    });
  });

  it("posts_severe_crash_when_selected", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);
    fireEvent.change(screen.getByTestId("crash-scenario-select"), {
      target: { value: "severe" },
    });
    fireEvent.click(screen.getByTestId("trigger-crash-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledWith({
        shock_type: "demand_crash",
        intensity: 1.0,
        scenario: "severe",
      });
    });
  });

  it("updates_crash_button_label_when_scenario_changes", () => {
    render(<ShocksControlPanel />);

    expect(screen.getByTestId("trigger-crash-btn").textContent).toBe("Запустить — Шок спроса");

    fireEvent.change(screen.getByTestId("crash-scenario-select"), {
      target: { value: "mild" },
    });
    expect(screen.getByTestId("trigger-crash-btn").textContent).toBe("Запустить — Слабый спад");

    fireEvent.change(screen.getByTestId("crash-scenario-select"), {
      target: { value: "severe" },
    });
    expect(screen.getByTestId("trigger-crash-btn").textContent).toBe("Запустить — Рецессия");
  });

  // ── Demand boom ──────────────────────────────────────────────────────────

  it("posts_demand_boom_standard_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_boom",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(screen.getByTestId("trigger-boom-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "demand_boom",
      intensity: 1.0,
      scenario: "standard",
    });
  });

  it("posts_severe_boom_when_selected", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_boom",
      queue_depth: 2,
    });

    render(<ShocksControlPanel />);
    fireEvent.change(screen.getByTestId("boom-scenario-select"), {
      target: { value: "severe" },
    });
    fireEvent.click(screen.getByTestId("trigger-boom-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledWith({
        shock_type: "demand_boom",
        intensity: 1.0,
        scenario: "severe",
      });
    });
  });

  it("updates_boom_button_label_when_scenario_changes", () => {
    render(<ShocksControlPanel />);

    expect(screen.getByTestId("trigger-boom-btn").textContent).toBe("Запустить — Сезонный бум");

    fireEvent.change(screen.getByTestId("boom-scenario-select"), {
      target: { value: "mild" },
    });
    expect(screen.getByTestId("trigger-boom-btn").textContent).toBe("Запустить — Оживление");

    fireEvent.change(screen.getByTestId("boom-scenario-select"), {
      target: { value: "severe" },
    });
    expect(screen.getByTestId("trigger-boom-btn").textContent).toBe("Запустить — Ажиотаж");
  });

  // ── Platform events ───────────────────────────────────────────────────────

  it("posts_marketplace_promotion_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "marketplace_promotion",
      queue_depth: 2,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(screen.getByTestId("trigger-promotion-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "marketplace_promotion",
      intensity: 1.0,
      duration_ticks: 15,
    });
  });

  it("posts_platform_fee_cut_on_click", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "platform_fee_cut",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);

    fireEvent.click(screen.getByTestId("trigger-fee-cut-btn"));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "platform_fee_cut",
      intensity: 1.0,
    });
  });

  // ── Success / error feedback ──────────────────────────────────────────────

  it("shows_queue_depth_message_on_success", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_crash",
      queue_depth: 3,
    });

    render(<ShocksControlPanel />);
    fireEvent.click(screen.getByTestId("trigger-crash-btn"));

    await waitFor(() => {
      expect(screen.getByText(/Событие в очереди \(глубина=3\)/)).toBeTruthy();
    });
  });

  it("shows_queue_depth_message_on_boom_success", async () => {
    triggerShock.mockResolvedValue({
      status: "queued",
      shock_type: "demand_boom",
      queue_depth: 1,
    });

    render(<ShocksControlPanel />);
    fireEvent.click(screen.getByTestId("trigger-boom-btn"));

    await waitFor(() => {
      expect(screen.getByText(/Событие в очереди \(глубина=1\)/)).toBeTruthy();
    });
  });

  // ── Disabled state ────────────────────────────────────────────────────────

  it("disables_all_controls_when_runtime_not_started", () => {
    render(<ShocksControlPanel disabled />);

    const crashSelect = screen.getByTestId("crash-scenario-select") as HTMLSelectElement;
    const boomSelect = screen.getByTestId("boom-scenario-select") as HTMLSelectElement;
    const crashBtn = screen.getByTestId("trigger-crash-btn") as HTMLButtonElement;
    const boomBtn = screen.getByTestId("trigger-boom-btn") as HTMLButtonElement;
    const promoBtn = screen.getByTestId("trigger-promotion-btn") as HTMLButtonElement;
    const feeCutBtn = screen.getByTestId("trigger-fee-cut-btn") as HTMLButtonElement;

    expect(crashSelect.disabled).toBe(true);
    expect(boomSelect.disabled).toBe(true);
    expect(crashBtn.disabled).toBe(true);
    expect(boomBtn.disabled).toBe(true);
    expect(promoBtn.disabled).toBe(true);
    expect(feeCutBtn.disabled).toBe(true);
    expect(screen.getByText("События доступны только после запуска симуляции.")).toBeTruthy();
  });

  // ── Crash and boom selects are independent ────────────────────────────────

  it("crash_and_boom_selects_are_independent", () => {
    render(<ShocksControlPanel />);

    fireEvent.change(screen.getByTestId("crash-scenario-select"), {
      target: { value: "severe" },
    });

    expect(screen.getByTestId("trigger-crash-btn").textContent).toBe("Запустить — Рецессия");
    expect(screen.getByTestId("trigger-boom-btn").textContent).toBe("Запустить — Сезонный бум");
  });
});
