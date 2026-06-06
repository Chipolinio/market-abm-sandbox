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
  severity: "warning",
};

describe("CyberEventTerminal", () => {
  it("prepends_new_events_at_bottom_with_flex_col_reverse", () => {
    render(<CyberEventTerminal lines={[newerLine, olderLine]} />);

    const scroll = screen.getByTestId("cyber-log-scroll");
    expect(scroll.className.split(/\s+/)).toContain("flex-col-reverse");

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
            severity: "warning",
          },
        ]}
      />,
    );

    expect(screen.getByText("[Tick 42] DEMAND_SHOCK: Buyer budgets cut by 30%")).toBeTruthy();
  });
});
