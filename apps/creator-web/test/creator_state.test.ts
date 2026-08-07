import {describe, expect, test} from "vitest";

import {
  creatorReducer,
  initialCreatorState,
  selectCanActivateAudio,
  selectCanTrigger,
  selectCreatorPhase,
  selectVisiblePads,
  type CreatorState,
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
    const pressed = creatorReducer(bankC, {
      type: "pad-pressed", slot: 32, outcome: "admitted",
    });
    expect(bankC.pressed.has(32)).toBe(false);
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
});
