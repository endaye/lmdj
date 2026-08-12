import {describe, expect, test} from "vitest";

import {
  creatorReducer,
  initialCreatorState,
  isCreatorActionAllowed,
  selectCanActivateAudio,
  selectCanTrigger,
  selectCreatorPhase,
  selectVisiblePads,
  type CreatorState,
  type CreatorAction,
  type ProjectView,
} from "../src/state/creator_state";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 4,
  bpm: 120,
  assetCount: 2,
  assignedPadCount: 2,
  bundleDigest: "a".repeat(64),
  key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({
    slot,
    assetId: slot === 0 || slot === 32 ? `asset-${slot}` : null,
  })),
};

function readyState(): CreatorState {
  return {
    ...initialCreatorState,
    project: {phase: "ready", projects: [], current: project},
    runtime: {phase: "ready", errorCode: null},
  };
}

describe("Creator state", () => {
  test("derives the exact orthogonal phase priority", () => {
    expect(selectCreatorPhase(initialCreatorState)).toBe("booting");
    expect(selectCreatorPhase({
      ...readyState(),
      project: {phase: "empty", projects: [], current: null},
    })).toBe("empty");
    expect(selectCreatorPhase({
      ...readyState(),
      transfer: {phase: "importing", completedBytes: 4, totalBytes: 8},
      audio: {phase: "running"},
    })).toBe("importing");
    expect(selectCreatorPhase({
      ...readyState(),
      project: {...readyState().project, phase: "opening"},
      audio: {phase: "running"},
    })).toBe("opening");
    expect(selectCreatorPhase(readyState())).toBe("ready");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "activating"},
    })).toBe("activating");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "running"},
    })).toBe("running");
    expect(selectCreatorPhase({
      ...readyState(), audio: {phase: "suspended"},
    })).toBe("suspended");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "unsupported", errorCode: "UNSUPPORTED_WEB_RUNTIME"},
    })).toBe("unsupported");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "restart-required", errorCode: "HOST_RESTART_REQUIRED"},
    })).toBe("restart-required");
    expect(selectCreatorPhase({
      ...readyState(), runtime: {phase: "closed", errorCode: null},
    })).toBe("closed");
    expect(selectCreatorPhase({
      ...readyState(), project: {...readyState().project, phase: "error"},
    })).toBe("failed");
  });

  test("selects one stable Bank and keeps pressed state immutable", () => {
    const bankC = creatorReducer(readyState(), {
      type: "bank-selected", bank: 2,
    });
    expect(selectVisiblePads(bankC).map(({slot}) => slot)).toEqual(
      Array.from({length: 16}, (_, index) => 32 + index),
    );
    const running = {
      ...bankC,
      audio: {phase: "running"} as const,
    };
    const pressed = creatorReducer(running, {
      type: "pad-pressed", slot: 32, outcome: "admitted",
    });
    expect(running.pressed.has(32)).toBe(false);
    expect(pressed.pressed.get(32)).toBe("admitted");
    const released = creatorReducer(pressed, {type: "pad-released", slot: 32});
    expect(released.pressed.has(32)).toBe(false);
  });

  test("gates activation and Trigger from authoritative substate", () => {
    const ready = readyState();
    expect(selectCanActivateAudio(ready)).toBe(true);
    expect(selectCanTrigger(ready)).toBe(false);
    const running = {...ready, audio: {phase: "running"} as const};
    expect(selectCanActivateAudio(running)).toBe(false);
    expect(selectCanTrigger(running)).toBe(true);
    expect(selectCanTrigger({
      ...running,
      transfer: {phase: "importing", completedBytes: 0, totalBytes: 1},
    })).toBe(false);
  });

  test.each<[string, CreatorState, CreatorAction]>([
    ["list while Runtime is booting", initialCreatorState, {type: "projects-listing"}],
    ["load before listing", readyState(), {type: "projects-loaded", projects: []}],
    ["open while listing", {
      ...readyState(), project: {...readyState().project, phase: "listing"},
    }, {type: "project-opening"}],
    ["publish Project before open or import", readyState(), {
      type: "project-ready", project,
    }],
    ["report Project error while idle", readyState(), {
      type: "project-error", errorCode: "IO_ERROR",
    }],
    ["start transfer while audio runs", {
      ...readyState(), audio: {phase: "running"},
    }, {type: "transfer-started", totalBytes: 8}],
    ["progress outside transfer", readyState(), {
      type: "transfer-progressed", completedBytes: 4,
    }],
    ["end absent transfer", readyState(), {type: "transfer-ended"}],
    ["activate without Project", {
      ...readyState(), project: {phase: "empty", projects: [], current: null},
    }, {type: "audio-changed", phase: "activating"}],
    ["recover without suspend", readyState(), {
      type: "audio-changed", phase: "recovering",
    }],
    ["select Bank while importing", {
      ...readyState(),
      transfer: {phase: "importing", completedBytes: 0, totalBytes: 8},
    }, {type: "bank-selected", bank: 1}],
    ["press while audio is inactive", readyState(), {
      type: "pad-pressed", slot: 0, outcome: "admitted",
    }],
    ["release a Pad that is not pressed", readyState(), {
      type: "pad-released", slot: 0,
    }],
  ])("rejects illegal %s from the reducer boundary", (_name, state, action) => {
    expect(isCreatorActionAllowed(state, action)).toBe(false);
    expect(creatorReducer(state, action)).toBe(state);
  });

  test("keeps lifecycle cleanup legal after the Runtime becomes terminal", () => {
    const state: CreatorState = {
      ...readyState(),
      runtime: {phase: "restart-required", errorCode: "HOST_TIMEOUT"},
      transfer: {phase: "importing", completedBytes: 4, totalBytes: 8},
      pressed: new Map([[0, "admitted"]]),
    };
    const cleared = creatorReducer(state, {type: "pressed-cleared"});
    expect(cleared.pressed.size).toBe(0);
    const ended = creatorReducer(cleared, {type: "transfer-ended"});
    expect(ended.transfer.phase).toBe("idle");
  });
});
