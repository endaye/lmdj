import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { padElementIds } from "../patch/loader";
import { activePlaybackRole } from "./playback";

describe("activePlaybackRole", () => {
  const patch = structuredClone(golden) as unknown as Patch;

  it("returns the actual public Pad role", () => {
    // Pad 1 is the Bass slot; the public role lives on the element it triggers.
    const ids = new Set(padElementIds(patch.pads[1]));
    expect(activePlaybackRole(patch, ids)).toBe("bass");
  });

  it("returns mixed when active elements span roles", () => {
    const ids = new Set([
      ...padElementIds(patch.pads[0]),
      ...padElementIds(patch.pads[1]),
    ]);
    expect(activePlaybackRole(patch, ids)).toBe("mixed");
  });

  it("returns null when no public Pad owns an active element", () => {
    expect(activePlaybackRole(patch, new Set(["unknown-element"]))).toBeNull();
  });
});
