import { afterEach, describe, expect, it, vi } from "vitest";
import { runChameleonViewTransition } from "./viewTransition";

afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, "startViewTransition");
});

function media(matches: boolean): MediaQueryList {
  return {
    matches,
    media: "(prefers-reduced-motion: reduce)",
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  };
}

describe("runChameleonViewTransition", () => {
  it("uses the browser transition when motion is allowed", () => {
    vi.stubGlobal("matchMedia", () => media(false));
    const start = vi.fn((update: () => void) => update());
    Object.assign(document, { startViewTransition: start });
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(start).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("updates synchronously when reduced motion is requested", () => {
    vi.stubGlobal("matchMedia", () => media(true));
    const start = vi.fn();
    Object.assign(document, { startViewTransition: start });
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(start).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledTimes(1);
  });

  it("updates synchronously when the API is unavailable", () => {
    vi.stubGlobal("matchMedia", () => media(false));
    const update = vi.fn();

    runChameleonViewTransition(update);

    expect(update).toHaveBeenCalledTimes(1);
  });
});
