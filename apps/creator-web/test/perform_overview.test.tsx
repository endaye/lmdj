import {render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {PerformOverview} from "../src/components/perform_overview";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";

const project = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
  patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 2 as const, events: []}],
  patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};
const state = {
  ...initialCreatorState,
  project: {...initialCreatorState.project, phase: "ready", current: project},
} as CreatorState;

test("stopped, the counter reads the Pattern's first beat", () => {
  render(<PerformOverview state={state} transport={initialPatternTransportState} />);
  expect(screen.getByTestId("perform-counter").textContent).toBe("BAR 01 / 02 · BEAT 01 / 04");
  expect(screen.getByRole("progressbar", {name: "Pattern position"}).getAttribute("aria-valuenow"))
    .toBe("0");
});

test("playing, the counter and progress follow the transport frames", () => {
  const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame").mockImplementation(() => 1);
  const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
  // Observed at 1000 ms on the origin; 750 ms later is 1440 ticks at 120 BPM.
  const now = vi.spyOn(performance, "now").mockReturnValue(1_750);
  try {
    render(<PerformOverview state={state} transport={{
      ...initialPatternTransportState,
      sessionId: "session-1",
      status: {
        engaged: true, playing: true, recording: false, phase: "idle",
        runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
        observedAtMilliseconds: 1_000, commandId: null, publicationPending: false, error: null,
      } satisfies PatternTransportStatus,
    }} />);
    expect(screen.getByTestId("perform-counter").textContent).toBe("BAR 01 / 02 · BEAT 02 / 04");
    expect(screen.getByRole("progressbar", {name: "Pattern position"}).getAttribute("aria-valuenow"))
      .toBe("1440");
    expect(screen.getByTestId("perform-overview").textContent).toContain("PLAYING");
  } finally {
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
    now.mockRestore();
  }
});
