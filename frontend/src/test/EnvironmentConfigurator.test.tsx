// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EnvironmentConfigurator } from "@/components/sidebar/EnvironmentConfigurator";

const configureSession = vi.fn();
const fetchSessionConfigure = vi.fn();

vi.mock("@/api/simulation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/simulation")>();
  return {
    ...actual,
    configureSession: (...args: unknown[]) => configureSession(...args),
    fetchSessionConfigure: (...args: unknown[]) => fetchSessionConfigure(...args),
  };
});

afterEach(() => {
  cleanup();
  configureSession.mockReset();
  fetchSessionConfigure.mockReset();
  localStorage.clear();
});

describe("EnvironmentConfigurator", () => {
  beforeEach(() => {
    fetchSessionConfigure.mockResolvedValue({
      n_buyers: 10_000,
      n_sellers: 50,
      seller_mix: { catboost_pct: 0.4, rule_based_pct: 0.35, basic_pct: 0.25 },
    });
  });

  it("disables_sliders_when_running", () => {
    render(<EnvironmentConfigurator disabled />);

    const sliders = screen.getAllByRole("slider");
    expect(sliders.length).toBeGreaterThan(0);
    for (const slider of sliders) {
      expect((slider as HTMLInputElement).disabled).toBe(true);
    }

    const applyButton = screen.getByRole("button", { name: "Применить" }) as HTMLButtonElement;
    expect(applyButton.disabled).toBe(true);
  });

  it("enables_sliders_when_configurable", () => {
    render(<EnvironmentConfigurator disabled={false} />);

    const sliders = screen.getAllByRole("slider");
    for (const slider of sliders) {
      expect((slider as HTMLInputElement).disabled).toBe(false);
    }
  });

  it("posts_configure_on_apply", async () => {
    configureSession.mockResolvedValue({ status: "accepted" });

    render(<EnvironmentConfigurator disabled={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Применить" }));

    await waitFor(() => {
      expect(configureSession).toHaveBeenCalledTimes(1);
    });

    expect(configureSession).toHaveBeenCalledWith({
      n_buyers: 10_000,
      n_sellers: 50,
      seller_mix: {
        catboost_pct: 0.4,
        rule_based_pct: 0.35,
        basic_pct: 0.25,
      },
    });

    await waitFor(() => {
      expect(screen.getByText("Configuration saved")).toBeTruthy();
    });
  });
});
