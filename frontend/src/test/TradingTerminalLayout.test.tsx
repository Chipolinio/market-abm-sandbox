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
  it("renders_four_zones_without_page_scroll", () => {
    const { container } = render(
      <TradingTerminalLayout metrics={null} connectionState="closed" workerState="IDLE" />,
    );

    const root = container.firstElementChild;
    expect(root).not.toBeNull();
    expect(hasClass(root!, "h-screen")).toBe(true);
    expect(hasClass(root!, "overflow-hidden")).toBe(true);
    expect(hasClass(root!, "flex-col")).toBe(true);

    const header = container.querySelector("header");
    expect(header).not.toBeNull();
    expect(hasClass(header!, "h-14")).toBe(true);

    const asides = container.querySelectorAll("aside");
    expect(asides).toHaveLength(2);
    expect(hasClass(asides[0]!, "w-80")).toBe(true);
    expect(hasClass(asides[1]!, "w-96")).toBe(true);
    expect(hasClass(asides[0]!, "overflow-y-auto")).toBe(true);

    const main = container.querySelector("main");
    expect(main).not.toBeNull();
    expect(hasClass(main!, "flex-1")).toBe(true);
    expect(hasClass(main!, "overflow-hidden")).toBe(true);
  });
});
