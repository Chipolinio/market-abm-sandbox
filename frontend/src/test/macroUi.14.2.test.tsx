// Spec 014 §13.2 — P0 UI Vitest (slice 14.2).
// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MacroRegimeBadge } from "@/components/header/MacroRegimeBadge";
import { MacroStatePanel } from "@/components/sidebar/MacroStatePanel";
import { ActiveShocksPanel } from "@/components/sidebar/ActiveShocksPanel";
import { NarrativeCard } from "@/components/center/NarrativeCard";
import { buildMacroNarrative } from "@/utils/buildMacroNarrative";
import type { ActiveShockDTO, MacroStateDTO } from "@/types/macro";

afterEach(() => {
  cleanup();
});

function stressMacro(overrides: Partial<MacroStateDTO> = {}): MacroStateDTO {
  return {
    regime: "stress",
    stress: 0.5,
    expansion: 0.0,
    stress_cap: 1.2,
    expansion_cap: 0.8,
    episode_id: 1,
    ticks_in_episode: 3,
    peak_stress: 0.5,
    peak_expansion: 0.0,
    est_recovery_eta_ticks: 28,
    ...overrides,
  };
}

describe("14.2 MacroRegimeBadge", () => {
  it("badge_renders_stress_pill", () => {
    render(<MacroRegimeBadge regime="stress" />);
    const pill = screen.getByTestId("macro-regime-badge");
    expect(pill.textContent).toContain("STRESS");
    expect(pill.className).toMatch(/red|stress/i);
  });

  it("hides_when_regime_null", () => {
    const { container } = render(<MacroRegimeBadge regime={null} />);
    expect(container.querySelector("[data-testid='macro-regime-badge']")).toBeNull();
  });
});

describe("14.2 MacroStatePanel", () => {
  it("macro_panel_bars_use_stress_cap", () => {
    render(
      <MacroStatePanel
        macro={stressMacro({ stress: 1.8, stress_cap: 2.0, expansion: 0.4, expansion_cap: 0.8 })}
      />,
    );
    const stressBar = screen.getByTestId("macro-stress-bar");
    expect(stressBar.getAttribute("style") ?? "").toMatch(/width:\s*90%/);
    const expansionBar = screen.getByTestId("macro-expansion-bar");
    expect(expansionBar.getAttribute("style") ?? "").toMatch(/width:\s*50%/);
    expect(screen.getByText(/episode\s*#1/i)).toBeTruthy();
    expect(screen.getByText(/~28/)).toBeTruthy();
  });

  it("stale_indicator_on_disconnect", () => {
    render(
      <MacroStatePanel
        macro={stressMacro()}
        connectionState="closed"
      />,
    );
    expect(screen.getByTestId("macro-stale-indicator").textContent).toMatch(
      /Stale|Disconnected/i,
    );
    expect(screen.getByTestId("macro-stress-bar")).toBeTruthy();
  });
});

describe("14.2 ActiveShocksPanel", () => {
  it("active_shocks_formats_scenario_and_ticks", () => {
    const shocks: ActiveShockDTO[] = [
      {
        shock_type: "demand_crash",
        intensity: 1.0,
        remaining_ticks: 12,
        applied_at_tick: 0,
        scenario: "severe",
      },
    ];
    render(<ActiveShocksPanel shocks={shocks} />);
    expect(screen.getByText(/DEMAND_CRASH severe · 12 ticks left/)).toBeTruthy();
  });

  it("shows_empty_copy_when_no_shocks", () => {
    render(<ActiveShocksPanel shocks={[]} />);
    expect(screen.getByText(/No active shocks/i)).toBeTruthy();
  });
});

describe("14.2 buildMacroNarrative", () => {
  it("narrative_templates_four_regimes", () => {
    const regimes = ["normal", "stress", "recovery", "expansion"] as const;
    const titles = regimes.map((regime) =>
      buildMacroNarrative(stressMacro({ regime }), []).title,
    );
    expect(new Set(titles).size).toBe(4);
  });

  it("pause_prefix_on_narrative", () => {
    const { title } = buildMacroNarrative(stressMacro(), [], { paused: true });
    expect(title.startsWith("[Пауза]")).toBe(true);
  });
});

describe("14.2 NarrativeCard", () => {
  it("renders_title_from_macro", () => {
    render(
      <NarrativeCard
        macro={stressMacro()}
        shocks={[]}
        workerState="RUNNING"
        connectionState="open"
      />,
    );
    expect(screen.getByTestId("narrative-card").textContent).toMatch(/Стресс|stress|episode/i);
  });

  it("shows_pause_prefix_when_paused", () => {
    render(
      <NarrativeCard
        macro={stressMacro()}
        shocks={[]}
        workerState="PAUSED"
        connectionState="open"
      />,
    );
    expect(screen.getByTestId("narrative-card").textContent).toMatch(/^\[Пауза\]/);
  });
});
