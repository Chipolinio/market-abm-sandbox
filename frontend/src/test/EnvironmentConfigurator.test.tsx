// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { EnvironmentConfigurator } from "@/components/sidebar/EnvironmentConfigurator";

afterEach(() => {
  cleanup();
});

describe("EnvironmentConfigurator", () => {
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
});
