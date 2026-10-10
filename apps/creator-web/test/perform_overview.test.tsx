import {act, render, screen} from "@testing-library/react";
import {expect, test, vi} from "vitest";

import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {PerformOverview, performPosition} from "../src/components/perform_overview";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {initialPatternTransportState} from "../src/state/pattern_transport_state";
import {initialPerformState, reducePerform, type PerformAction, type PerformState} from "../src/state/perform_state";

const project = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null, category: null, colourOverride: null, colour: null})),
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
        currentPatternId: null, pendingSwitch: null,
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

test("a tick from a longer Pattern is held inside the new length", () => {
  expect(performPosition(null, 384)).toBe(0);
  expect(performPosition(200, 384)).toBe(200);
  expect(performPosition(1_500, 384)).toBe(383);
});

test("a pending launch preserves the acknowledged slot and clears on failure or session reset", () => {
  let value: PerformState = {...initialPerformState({state: "unconfigured", config: null, error: null}),
    lastLaunchAck: {requestId: "first", patternSlot: 0, effectiveTick: 1920}};
  const listeners = new Set<() => void>();
  const controller = {
    getState: () => value,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    connect: vi.fn(), leave: vi.fn(),
  };
  const update = (action: PerformAction) => act(() => {
    value = reducePerform(value, action);
    for (const listener of listeners) listener();
  });
  const view = render(<PerformOverview state={state} controller={controller} />);
  const cue = () => screen.getByLabelText("Pattern launch cue").textContent;
  expect(cue()).toBe("ACKNOWLEDGED SLOT 01 · NOTHING QUEUED");
  update({type: "pending-launch", pending: {requestId: "next", patternSlot: 1,
    targetTick: 3840, claimed: false}});
  expect(cue()).toBe("ACKNOWLEDGED SLOT 01 → QUEUED SLOT 02");
  update({type: "error", message: "Launch was refused"});
  update({type: "pending-launch", pending: null});
  expect(cue()).toBe("ACKNOWLEDGED SLOT 01 · NOTHING QUEUED");
  update({type: "session-neutral"});
  expect(cue()).toBe("LAST LAUNCH — · NOTHING QUEUED");
  expect(view.container.querySelector("button,input,select,[tabindex]" )).toBeNull();
  view.unmount();
  expect(listeners.size).toBe(0);
  expect(controller.connect).not.toHaveBeenCalled();
  expect(controller.leave).not.toHaveBeenCalled();
});

// #1958: without a Performance launch pending, the playing transport's queued
// switch names its slot in the same cue.
test("the transport's queued switch names its slot when no Performance launch is pending", () => {
  const slottedProject = {
    ...project,
    patternSlots: Object.freeze([
      null, project.patterns[0]!.patternId,
      ...Array<string | null>(14).fill(null),
    ]),
  };
  const slottedState = {
    ...initialCreatorState,
    project: {...initialCreatorState.project, phase: "ready" as const,
      current: slottedProject},
  } as CreatorState;
  const view = render(<PerformOverview state={slottedState}
    transport={initialPatternTransportState} />);
  expect(screen.getByLabelText("Pattern launch cue").textContent)
    .toBe("LAST LAUNCH — · NOTHING QUEUED");
  view.rerender(<PerformOverview state={slottedState} transport={{
    ...initialPatternTransportState,
    sessionId: "session-1",
    status: {
      engaged: true, playing: true, recording: false, phase: "idle",
      runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
      observedAtMilliseconds: 0, commandId: null, publicationPending: false,
      error: null, currentPatternId: null,
      pendingSwitch: {patternId: project.patterns[0]!.patternId, activationFrame: 96_000},
    },
  }} />);
  expect(screen.getByLabelText("Pattern launch cue").textContent)
    .toBe("LAST LAUNCH — → QUEUED SLOT 02");
});
