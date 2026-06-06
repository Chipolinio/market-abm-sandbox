// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CyberEventTerminal } from "@/components/cyberlog/CyberEventTerminal";
import type { CyberLogLine } from "@/state/cyberLog";

afterEach(() => {
  cleanup();
});

const newerLine: CyberLogLine = {
  event_id: "evt-2",
  tick_id: 10,
  display_code: "FLASH_CRASH",
  message: "Market median price dropped 40% over 5 ticks",
  severity: "critical",
};

const olderLine: CyberLogLine = {
  event_id: "evt-1",
  tick_id: 5,
  display_code: "DEMAND_SHOCK",
  message: "Buyer budgets cut by 30%",
  severity: "info",
};

describe("CyberEventTerminal", () => {
  it("renders_cyber_log_header", () => {
    render(<CyberEventTerminal lines={[]} />);
    expect(screen.getByText("Микро-лог")).toBeTruthy();
  });

  it("shows_waiting_placeholder_when_empty", () => {
    render(<CyberEventTerminal lines={[]} />);
    expect(screen.getByText("Ожидание событий…")).toBeTruthy();
  });

  it("prepends_new_events_at_bottom_with_flex_col_reverse", () => {
    render(<CyberEventTerminal lines={[newerLine, olderLine]} />);

    const scroll = screen.getByTestId("cyber-log-scroll");
    expect(scroll.className.split(/\s+/)).toContain("flex-col-reverse");
    expect(scroll.className.split(/\s+/)).toContain("font-mono");

    const rendered = screen.getAllByTestId("cyber-log-line");
    expect(rendered[0]?.textContent).toContain("FLASH_CRASH");
    expect(rendered[1]?.textContent).toContain("DEMAND_SHOCK");
  });

  it("formats_tick_prefix", () => {
    render(
      <CyberEventTerminal
        lines={[
          {
            event_id: "evt-42",
            tick_id: 42,
            display_code: "DEMAND_SHOCK",
            message: "Buyer budgets cut by 30%",
            severity: "info",
          },
        ]}
      />,
    );

    expect(screen.getByText("[Тик 42] DEMAND_SHOCK: Buyer budgets cut by 30%")).toBeTruthy();
  });

  it("applies_severity_classes_by_display_code", () => {
    render(
      <CyberEventTerminal
        lines={[
          {
            event_id: "evt-crash",
            tick_id: 12,
            display_code: "FLASH_CRASH",
            message: "Market median price dropped 40% over 10 ticks",
            severity: "info",
          },
          {
            event_id: "evt-war",
            tick_id: 8,
            display_code: "PRICING_WAR",
            message: "Seller_1 and Seller_3 entered a dumping loop",
            severity: "info",
          },
        ]}
      />,
    );

    const lines = screen.getAllByTestId("cyber-log-line");
    expect(lines[0]?.className.split(/\s+/)).toContain("text-red-400");
    expect(lines[1]?.className.split(/\s+/)).toContain("text-amber-400");
  });

  it("collapses_mass_bankruptcy_events", () => {
    const lines: CyberLogLine[] = Array.from({ length: 4 }, (_, index) => ({
      event_id: `bk-${index}`,
      tick_id: 99,
      display_code: "BANKRUPTCY" as const,
      message: `Seller ${index}`,
      severity: "info" as const,
    }));

    render(<CyberEventTerminal lines={lines} />);

    const rendered = screen.getAllByTestId("cyber-log-line");
    expect(rendered).toHaveLength(1);
    expect(rendered[0]?.textContent).toContain("Массовое выбывание алгоритмов (4 игроков)");
  });
});
