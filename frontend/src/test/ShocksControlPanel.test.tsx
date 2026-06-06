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

    fireEvent.click(screen.getByRole("button", { name: "Запустить шок спроса" }));

    await waitFor(() => {
      expect(triggerShock).toHaveBeenCalledTimes(1);
    });
    expect(triggerShock).toHaveBeenCalledWith({
      shock_type: "demand_crash",
      intensity: 1.0,
      duration_ticks: 10,
    });
  });
});
