// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TradingTerminalLayout } from "@/layouts/TradingTerminalLayout";

afterEach(() => {
  cleanup();
});

function hasClass(el: Element, className: string): boolean {
  return el.className.split(/\s+/).includes(className);
}

describe("TradingTerminalLayout", () => {
  it("root locks viewport height", () => {
    const { container } = render(
      <TradingTerminalLayout metrics={null} connectionState="closed" workerState="IDLE" />,
    );

    const root = container.firstElementChild;
    expect(root).not.toBeNull();
    expect(hasClass(root!, "h-screen")).toBe(true);
    expect(hasClass(root!, "w-screen")).toBe(true);
    expect(hasClass(root!, "overflow-hidden")).toBe(true);
    expect(hasClass(root!, "flex-col")).toBe(true);
  });

  it("four_zones_present", () => {
    const { container } = render(
      <TradingTerminalLayout metrics={null} connectionState="closed" workerState="IDLE" />,
    );

    const topBar = container.querySelector('[data-testid="zone-top-bar"]');
    expect(topBar).not.toBeNull();
    expect(hasClass(topBar!, "h-14")).toBe(true);
    expect(hasClass(topBar!, "w-full")).toBe(true);

    const leftSidebar = container.querySelector('[data-testid="zone-left-sidebar"]');
    expect(leftSidebar).not.toBeNull();
    expect(hasClass(leftSidebar!, "w-80")).toBe(true);
    expect(hasClass(leftSidebar!, "overflow-y-auto")).toBe(true);
    expect(hasClass(leftSidebar!, "bg-white")).toBe(true);

    const main = container.querySelector('[data-testid="zone-main"]');
    expect(main).not.toBeNull();
    expect(hasClass(main!, "flex-1")).toBe(true);
    expect(hasClass(main!, "overflow-hidden")).toBe(true);

    const cyberlog = container.querySelector('[data-testid="zone-cyberlog"]');
    expect(cyberlog).not.toBeNull();
    expect(hasClass(cyberlog!, "w-96")).toBe(true);
    expect(hasClass(cyberlog!, "bg-white")).toBe(true);
    expect(container.querySelector('[data-testid="top-sellers-dashboard"]')).not.toBeNull();
  });

  it("main_area_no_page_scroll", () => {
    const { container } = render(
      <TradingTerminalLayout metrics={null} connectionState="closed" workerState="IDLE" />,
    );

    const root = container.firstElementChild!;
    expect(hasClass(root, "overflow-hidden")).toBe(true);

    const mainRow = root.querySelector(".flex.min-h-0.flex-1.overflow-hidden");
    expect(mainRow).not.toBeNull();

    const main = container.querySelector('[data-testid="zone-main"]');
    expect(main).not.toBeNull();
    expect(hasClass(main!, "overflow-hidden")).toBe(true);

    const leftSidebar = container.querySelector('[data-testid="zone-left-sidebar"]');
    expect(leftSidebar).not.toBeNull();
    expect(hasClass(leftSidebar!, "overflow-y-auto")).toBe(true);
  });
});
