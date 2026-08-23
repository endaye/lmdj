import {describe, expect, test} from "vitest";
import {DEFAULT_KEYBOARD_MAPPING} from "@lmdj/web-runtime-platform/input_adapters.mjs";

import {createCreatorInputController} from "../src/runtime/input_controller";
import type {
  CreatorSampleRuntimeSession,
  CreatorRuntimeSession,
  PadPlayback,
  RuntimeHostState,
  RuntimeOutcome,
  RuntimeVoiceState,
  SampleInspect,
  SampleTriggerMode,
} from "../src/runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  type CreatorAction,
  type CreatorState,
} from "../src/state/creator_state";

const TEST_PRODUCT_BUILD = "9.8.7.6";

function fakeMidiInput() {
  const listeners = new Map<string, (event: unknown) => void>();
  return {
    type: "input",
    state: "connected",
    addEventListener(type: string, listener: (event: unknown) => void) {
      listeners.set(type, listener);
    },
    removeEventListener(type: string, listener: (event: unknown) => void) {
      if (listeners.get(type) === listener) listeners.delete(type);
    },
    emit(data: readonly number[]) {
      listeners.get("midimessage")?.({data: Uint8Array.from(data)});
    },
    listenerCount() {
      return listeners.size;
    },
  };
}

function fakeMidiAccess(input: ReturnType<typeof fakeMidiInput>) {
  const listeners = new Map<string, (event: unknown) => void>();
  return {
    inputs: new Map([["input", input]]),
    addEventListener(type: string, listener: (event: unknown) => void) {
      listeners.set(type, listener);
    },
    removeEventListener(type: string, listener: (event: unknown) => void) {
      if (listeners.get(type) === listener) listeners.delete(type);
    },
    listenerCount() {
      return listeners.size;
    },
  };
}

function fixture() {
  const triggers: Array<{slot: number; velocity: number; source: string}> = [];
  const outcomeListeners = new Set<(outcome: RuntimeOutcome) => void>();
  const hostListeners = new Set<(state: RuntimeHostState) => void>();
  let nextSequence = 1;
  let state: CreatorState = {
    ...initialCreatorState,
    project: {
      phase: "ready",
      projects: [],
      current: {
        projectId: "11111111-1111-4111-8111-111111111111",
        patternId: "22222222-2222-4222-8222-222222222222",
        revision: 42,
        bpm: 120,
        assetCount: 64,
        assignedPadCount: 64,
        bundleDigest: "a".repeat(64),
        key: "—",
        pads: Array.from({length: 64}, (_, slot) => ({
          slot,
          assetId: `asset-${slot}`,
        })),
      },
    },
    runtime: {phase: "ready", errorCode: null},
    audio: {phase: "running"},
  };
  const actions: CreatorAction[] = [];
  const session: CreatorRuntimeSession = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => [],
    importProject: async () => { throw new Error("unused"); },
    openProject: async () => ({}),
    inspectProject: async () => ({}),
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async (slot, velocity, source) => {
      triggers.push({slot, velocity, source});
      return {sequence: nextSequence++, slot, velocity, source};
    },
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState(listener) {
      hostListeners.add(listener);
      return () => hostListeners.delete(listener);
    },
    subscribeRuntimeOutcome(listener) {
      outcomeListeners.add(listener);
      return () => outcomeListeners.delete(listener);
    },
    diagnostics: () => ({
      state: "running",
      error_code: null,
      error_details: {},
      product_build: TEST_PRODUCT_BUILD,
      host_id: "creator-web",
      host_version: "1.3.5",
      platform_version: "0.3.4",
      protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: triggers.length,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
  };
  return {
    session,
    triggers,
    dispatch(action: CreatorAction) {
      actions.push(action);
      state = creatorReducer(state, action);
    },
    actions,
    state: () => state,
    selectBank(bank: 0 | 1 | 2 | 3) {
      state = creatorReducer(state, {type: "bank-selected", bank});
    },
    outcome(outcome: RuntimeOutcome) {
      for (const listener of outcomeListeners) listener(outcome);
    },
  };
}

function sampleInspect(
  slot: number,
  triggerMode: SampleTriggerMode = "one_shot",
  assetId: string | null = "11111111-1111-4111-8111-111111111111",
): SampleInspect {
  return {
    projectRevision: 42,
    slot,
    assetId,
    playback: {
      trimStartFrame: 0,
      trimEndFrame: assetId === null ? null : 1_000,
      triggerMode,
      gainMillidb: 0,
      muted: false,
    },
    metadata: assetId === null
      ? null
      : {sampleRate: 48_000, channels: 2, sourceFrames: 1_000},
    waveformCacheIdentity: assetId === null
      ? null
      : `${"a".repeat(64)}/1/max-abs-mirror/2`,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

interface SampleFixtureOptions {
  isAssigned?: (slot: number) => boolean;
  isAvailable?: (slot: number) => boolean;
  isRuntimeCurrent?: () => boolean;
  inspectSample?: (slot: number) => Promise<SampleInspect>;
  getAuditionPlayback?: (slot: number) => PadPlayback | null;
}

function sampleFixture(options: SampleFixtureOptions = {}) {
  const value = fixture();
  const releases: Array<{slot: number; source: string}> = [];
  const stopped: number[] = [];
  const voiceListeners = new Set<(event: RuntimeVoiceState) => void>();
  let stopAllCount = 0;
  const inspectCalls: number[] = [];
  const filePickIntents: Array<{slot: number; source: string}> = [];
  const session: CreatorSampleRuntimeSession = {
    ...value.session,
    async inspectSample(slot) {
      inspectCalls.push(slot);
      return options.inspectSample?.(slot) ?? sampleInspect(slot);
    },
    queryWaveform: async () => { throw new Error("unused"); },
    importAssignSample: async () => { throw new Error("unused"); },
    updatePad: async () => { throw new Error("unused"); },
    resetPad: async () => { throw new Error("unused"); },
    setSamplePreview: async (_slot: number, _playback: PadPlayback) => true,
    clearSamplePreview: async () => true,
    async release(slot, source) {
      releases.push({slot, source});
      return true;
    },
    async stopPad(slot) {
      stopped.push(slot);
      return true;
    },
    async stopAll() {
      stopAllCount += 1;
      return true;
    },
    retryPrepare: async () => { throw new Error("unused"); },
    subscribeVoiceState(listener: (event: RuntimeVoiceState) => void) {
      voiceListeners.add(listener);
      return () => voiceListeners.delete(listener);
    },
  };
  const controller = createCreatorInputController({
    session,
    getActiveBank: () => 0,
    isAssigned: options.isAssigned ?? (() => true),
    isAvailable: options.isAvailable ?? (() => true),
    isRuntimeCurrent: options.isRuntimeCurrent ?? (() => true),
    getAuditionPlayback: options.getAuditionPlayback ?? ((slot) => {
      const sample = value.state().sample;
      return sample.selectedSlot === slot ? sample.auditionPlayback : null;
    }),
    onFilePickIntent(slot, source) {
      filePickIntents.push({slot, source});
    },
    dispatch: value.dispatch,
  });
  return {
    ...value,
    session,
    controller,
    releases,
    stopped,
    stopAllCount: () => stopAllCount,
    inspectCalls,
    filePickIntents,
    voice(event: RuntimeVoiceState) {
      for (const listener of voiceListeners) listener(event);
    },
    voiceListenerCount: () => voiceListeners.size,
  };
}

async function settle() {
  for (let count = 0; count < 8; count += 1) await Promise.resolve();
}

describe("Creator input controller", () => {
  test("selects an empty Pad and emits file-pick intent without an audio trigger", () => {
    const value = sampleFixture({isAssigned: () => false});
    const target = document.createElement("button");
    expect(value.controller.pointerDown({
      type: "pointerdown",
      isPrimary: true,
      button: 0,
      pointerId: 9,
      clientX: 10,
      clientY: 20,
      target,
    }, 5)).toBe(true);
    expect(value.state().sample.selectedSlot).toBe(5);
    expect(value.filePickIntents).toEqual([{slot: 5, source: "pointer"}]);
    expect(value.inspectCalls).toEqual([]);
    expect(value.triggers).toEqual([]);
    expect(value.controller.pointerUp({pointerId: 9}, 5)).toBe(true);
    expect(value.releases).toEqual([]);
    expect(value.state().pressed.has(5)).toBe(false);
    value.controller.dispose();
  });

  test("selects an assigned unavailable Pad without triggering or file intent", () => {
    const value = sampleFixture({isAvailable: () => false});
    expect(value.controller.keyDown({
      code: "KeyQ",
      repeat: false,
      target: document.body,
    })).toBe(true);
    expect(value.state().sample.selectedSlot).toBe(0);
    expect(value.triggers).toEqual([]);
    expect(value.filePickIntents).toEqual([]);
    expect(value.inspectCalls).toEqual([]);
    expect(value.state().pressed.has(0)).toBe(false);
    expect(value.controller.keyUp({code: "KeyQ"})).toBe(true);
    expect(value.releases).toEqual([]);
    value.controller.dispose();
  });

  test.each([
    ["one_shot", false],
    ["gate", true],
    ["loop_gate", true],
  ] as const)(
    "selects and triggers assigned %s with mode-aware key release",
    async (mode, expectsRelease) => {
      const value = sampleFixture({
        inspectSample: async (slot) => sampleInspect(slot, mode),
      });
      expect(value.controller.keyDown({
        code: "KeyQ",
        repeat: false,
        target: document.body,
      })).toBe(true);
      await settle();
      expect(value.state().sample.selectedSlot).toBe(0);
      expect(value.triggers).toEqual([
        {slot: 0, velocity: 100, source: "keyboard"},
      ]);
      expect(value.state().pressed.get(0)).toBe("admitted");

      expect(value.controller.keyUp({code: "KeyQ"})).toBe(true);
      await settle();
      expect(value.state().pressed.has(0)).toBe(false);
      expect(value.releases).toEqual(expectsRelease
        ? [{slot: 0, source: "keyboard"}]
        : []);
      value.controller.dispose();
    },
  );

  test("uses a loop-toggle second press to stop without a duplicate trigger", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    expect(value.controller.keyDown({
      code: "KeyQ",
      repeat: false,
      target: document.body,
    })).toBe(true);
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    expect(value.controller.keyUp({code: "KeyQ"})).toBe(true);
    expect(value.state().pressed.get(0)).toBe("started");
    expect(value.releases).toEqual([]);

    expect(value.controller.keyDown({
      code: "KeyQ",
      repeat: false,
      target: document.body,
    })).toBe(true);
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.inspectCalls).toEqual([0]);
    expect(value.stopped).toEqual([0]);
    expect(value.state().pressed.has(0)).toBe(false);
    expect(value.controller.keyUp({code: "KeyQ"})).toBe(true);
    expect(value.releases).toEqual([]);
    value.controller.dispose();
  });

  test("stops a loop-toggle accepted before its Voice outcome without a duplicate trigger", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});

    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();

    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    value.controller.dispose();
  });

  test("preserves a loop latch across public physical clear for Bank changes", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.clearPressed();
    await settle();
    expect(value.stopAllCount()).toBe(0);
    expect(value.state().pressed.size).toBe(0);
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    value.controller.dispose();
  });

  test("preserves a pending loop admission across public physical clear", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    value.controller.clearPressed();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    await settle();

    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();

    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    value.controller.dispose();
  });

  test("public physical clear releases a held gate without owning stop-all", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "gate"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.clearPressed();
    await settle();
    expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
    expect(value.stopAllCount()).toBe(0);
    expect(value.state().pressed.size).toBe(0);
    value.controller.dispose();
  });

  test("adverse lifecycle clears gestures and latches without duplicate controls", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    window.dispatchEvent(new Event("blur"));
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(2);
    expect(value.stopped).toEqual([]);
    expect(value.releases).toEqual([]);
    expect(value.stopAllCount()).toBe(0);
    value.controller.dispose();
  });

  test.each([
    ["one_shot", true],
    ["gate", false],
    ["loop_gate", false],
    ["loop_toggle", true],
  ] as const)(
    "resolves a normal release before %s inspect with exact mode semantics",
    async (mode, expectsTrigger) => {
      const pending = deferred<SampleInspect>();
      const value = sampleFixture({inspectSample: () => pending.promise});
      expect(value.controller.keyDown({
        code: "KeyQ",
        repeat: false,
        target: document.body,
      })).toBe(true);
      expect(value.inspectCalls).toEqual([0]);
      expect(value.controller.keyUp({code: "KeyQ"})).toBe(true);
      pending.resolve(sampleInspect(0, mode));
      await settle();
      expect(value.triggers).toHaveLength(expectsTrigger ? 1 : 0);
      expect(value.releases).toEqual([]);
      expect(value.state().pressed.has(0)).toBe(false);
      value.controller.dispose();
    },
  );

  test("serializes rapid Sample inspect and trigger journeys across Pads", async () => {
    const first = deferred<SampleInspect>();
    const value = sampleFixture({
      inspectSample: (slot) => slot === 0
        ? first.promise
        : Promise.resolve(sampleInspect(slot, "one_shot")),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyW", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyW"});
    await settle();

    expect(value.inspectCalls).toEqual([0]);
    expect(value.triggers).toEqual([]);

    first.resolve(sampleInspect(0, "one_shot"));
    await settle();
    await settle();
    expect(value.inspectCalls).toEqual([0, 1]);
    expect(value.triggers.map(({slot}) => slot)).toEqual([0, 1]);
    value.controller.dispose();
  });

  test("preserves distinct rapid presses on the same Pad while inspect is pending", async () => {
    const first = deferred<SampleInspect>();
    let inspectCount = 0;
    const value = sampleFixture({
      inspectSample: (slot) => {
        inspectCount += 1;
        return inspectCount === 1
          ? first.promise
          : Promise.resolve(sampleInspect(slot, "one_shot"));
      },
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    await settle();

    expect(value.inspectCalls).toEqual([0]);
    expect(value.triggers).toEqual([]);

    first.resolve(sampleInspect(0, "one_shot"));
    await settle();
    await settle();
    expect(value.inspectCalls).toEqual([0, 0]);
    expect(value.triggers.map(({slot}) => slot)).toEqual([0, 0]);
    value.controller.dispose();
  });

  test("turns a queued second loop-toggle press into a stop after first admission", async () => {
    const first = deferred<SampleInspect>();
    let inspectCount = 0;
    const value = sampleFixture({
      inspectSample: (slot) => {
        inspectCount += 1;
        return inspectCount === 1
          ? first.promise
          : Promise.resolve(sampleInspect(slot, "loop_toggle"));
      },
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    await settle();

    first.resolve(sampleInspect(0, "loop_toggle"));
    await settle();
    await settle();

    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    value.controller.dispose();
  });

  test("preserves released queued one-shots across a public Bank clear", async () => {
    const first = deferred<SampleInspect>();
    const value = sampleFixture({
      inspectSample: (slot) => slot === 0
        ? first.promise
        : Promise.resolve(sampleInspect(slot, "one_shot")),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyW", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyW"});
    value.controller.clearPressed();
    await settle();

    expect(value.inspectCalls).toEqual([0]);
    first.resolve(sampleInspect(0, "one_shot"));
    await settle();
    await settle();
    expect(value.inspectCalls).toEqual([0, 1]);
    expect(value.triggers.map(({slot}) => slot)).toEqual([0, 1]);
    value.controller.dispose();
  });

  test("always cancels pointercancel before inspect resolves", async () => {
    const pending = deferred<SampleInspect>();
    const value = sampleFixture({inspectSample: () => pending.promise});
    value.controller.pointerDown({
      type: "pointerdown",
      isPrimary: true,
      button: 0,
      pointerId: 7,
      clientX: 10,
      clientY: 20,
      target: document.body,
    }, 0);
    expect(value.controller.pointerCancel({pointerId: 7}, 0)).toBe(true);
    pending.resolve(sampleInspect(0, "one_shot"));
    await settle();
    expect(value.triggers).toEqual([]);
    value.controller.dispose();
  });

  test("pointercancel releases an already-triggered gate", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "gate"),
    });
    value.controller.pointerDown({
      type: "pointerdown",
      isPrimary: true,
      button: 0,
      pointerId: 8,
      clientX: 10,
      clientY: 20,
      target: document.body,
    }, 0);
    await settle();
    value.controller.pointerCancel({pointerId: 8}, 0);
    await settle();
    expect(value.releases).toEqual([{slot: 0, source: "pointer"}]);
    value.controller.dispose();
  });

  test("releases from accepted preview gate mode instead of saved one-shot", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "one_shot"),
    });
    const inspected = sampleInspect(0, "one_shot");
    value.dispatch({type: "sample-action", action: {type: "slot-selected", slot: 0}});
    value.dispatch({type: "sample-action", action: {type: "inspect-stored", inspect: inspected}});
    value.dispatch({type: "sample-action", action: {type: "draft-began"}});
    value.dispatch({
      type: "sample-action",
      action: {type: "draft-updated", changes: {triggerMode: "gate"}},
    });
    value.dispatch({
      type: "sample-action",
      action: {
        type: "preview-applied",
        playback: value.state().sample.draft?.proposed,
      } as never,
    });

    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    await settle();
    expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
    value.controller.dispose();
  });

  test("does not create a loop latch from saved mode when preview is one-shot", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    const inspected = sampleInspect(0, "loop_toggle");
    value.dispatch({type: "sample-action", action: {type: "slot-selected", slot: 0}});
    value.dispatch({type: "sample-action", action: {type: "inspect-stored", inspect: inspected}});
    value.dispatch({type: "sample-action", action: {type: "draft-began"}});
    value.dispatch({
      type: "sample-action",
      action: {type: "draft-updated", changes: {triggerMode: "one_shot"}},
    });
    value.dispatch({
      type: "sample-action",
      action: {
        type: "preview-applied",
        playback: value.state().sample.draft?.proposed,
      } as never,
    });

    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(2);
    expect(value.stopped).toEqual([]);
    value.controller.dispose();
  });

  test("ignores a stale inspect after the same gesture is released and pressed again", async () => {
    const first = deferred<SampleInspect>();
    const second = deferred<SampleInspect>();
    let call = 0;
    const value = sampleFixture({
      inspectSample: () => (call++ === 0 ? first.promise : second.promise),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    first.resolve(sampleInspect(0, "gate"));
    await settle();
    expect(value.triggers).toEqual([]);

    second.resolve(sampleInspect(0, "loop_gate"));
    await settle();
    expect(value.triggers).toEqual([
      {slot: 0, velocity: 100, source: "keyboard"},
    ]);
    value.controller.keyUp({code: "KeyQ"});
    await settle();
    expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
    value.controller.dispose();
  });

  test("uses authoritative empty inspect without triggering stale assigned truth", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "one_shot", null),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toEqual([]);
    expect(value.filePickIntents).toEqual([{slot: 0, source: "keyboard"}]);
    expect(value.state().pressed.has(0)).toBe(false);
    value.controller.keyUp({code: "KeyQ"});
    value.controller.dispose();
  });

  test.each(["one_shot", "gate"] as const)(
    "uses mode-agnostic published Runtime controls across saved %s Cook split",
    async (savedMode) => {
      const value = sampleFixture({
        isRuntimeCurrent: () => false,
        inspectSample: async (slot) => sampleInspect(slot, savedMode),
      });
      value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
      await settle();
      value.controller.keyUp({code: "KeyQ"});
      await settle();
      expect(value.inspectCalls).toEqual([]);
      expect(value.triggers).toEqual([
        {slot: 0, velocity: 100, source: "keyboard"},
      ]);
      expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
      expect(value.stopped).toEqual([]);
      value.controller.dispose();
    },
  );

  test("pointercancel safely releases an already-triggered Cook-split gesture", async () => {
    const value = sampleFixture({isRuntimeCurrent: () => false});
    value.controller.pointerDown({
      type: "pointerdown",
      isPrimary: true,
      button: 0,
      pointerId: 11,
      clientX: 10,
      clientY: 20,
      target: document.body,
    }, 0);
    await settle();
    value.controller.pointerCancel({pointerId: 11}, 0);
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.releases).toEqual([{slot: 0, source: "pointer"}]);
    value.controller.dispose();
  });

  test("switches to mode-agnostic controls if Runtime becomes stale during inspect", async () => {
    const pending = deferred<SampleInspect>();
    let runtimeCurrent = true;
    const value = sampleFixture({
      isRuntimeCurrent: () => runtimeCurrent,
      inspectSample: () => pending.promise,
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    runtimeCurrent = false;
    pending.resolve(sampleInspect(0, "one_shot"));
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
    value.controller.dispose();
  });

  test("unlatches loop-toggle on capacity so the next press retries", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_capacity", runtimeFrame: 128});
    expect(value.state().pressed.get(0)).toBe("capacity");
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(2);
    expect(value.inspectCalls).toEqual([0, 0]);
    expect(value.stopped).toEqual([]);
    value.controller.dispose();
  });

  test("does not latch a muted loop-toggle without authoritative Voice start", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => {
        const inspected = sampleInspect(slot, "loop_toggle");
        return {...inspected, playback: {...inspected.playback, muted: true}};
      },
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(2);
    expect(value.inspectCalls).toEqual([0, 0]);
    expect(value.stopped).toEqual([]);
    value.controller.dispose();
  });

  test("stops an existing latch before reassessing assignment or availability", async () => {
    let assigned = true;
    let available = true;
    const value = sampleFixture({
      isAssigned: () => assigned,
      isAvailable: () => available,
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    assigned = false;
    available = false;
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    expect(value.filePickIntents).toEqual([]);
    value.controller.dispose();
  });

  test("reconciles loop latches from authoritative Voice stop and unsubscribes", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    expect(value.voiceListenerCount()).toBe(1);
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.voice({
      sequence: 1,
      slot: 0,
      state: "started",
      runtimeFrame: 128,
      sourceFrame: 100,
    });
    expect(value.state().sample.voices).toHaveLength(1);
    value.controller.keyUp({code: "KeyQ"});
    value.voice({
      sequence: 1,
      slot: 0,
      state: "stopped",
      runtimeFrame: 256,
      sourceFrame: 100,
    });
    expect(value.state().sample.voices).toHaveLength(0);
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(2);
    expect(value.stopped).toEqual([]);
    value.controller.dispose();
    expect(value.voiceListenerCount()).toBe(0);
  });

  test("ignores an unrelated Voice completion when reconciling a loop latch", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    value.voice({
      sequence: 99,
      slot: 0,
      state: "completed",
      runtimeFrame: 256,
      sourceFrame: 100,
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0]);
    value.controller.dispose();
  });

  test("does not let an old Voice completion erase a newer held gate", async () => {
    let inspectCount = 0;
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(
        slot,
        inspectCount++ === 0 ? "one_shot" : "gate",
      ),
    });
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.voice({
      sequence: 1,
      slot: 0,
      state: "completed",
      runtimeFrame: 256,
      sourceFrame: 100,
    });
    value.controller.keyUp({code: "KeyQ"});
    await settle();
    expect(value.releases).toEqual([{slot: 0, source: "keyboard"}]);
    value.controller.dispose();
  });

  test("keeps a latch and fails Runtime state when stopPad returns false", async () => {
    const value = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "loop_toggle"),
    });
    value.session.stopPad = async (slot) => {
      value.stopped.push(slot);
      return false;
    };
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    value.controller.keyUp({code: "KeyQ"});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.stopped).toEqual([0, 0]);
    expect(value.actions).toContainEqual({
      type: "runtime-changed",
      phase: "failed",
      errorCode: "HOST_STATE_INVALID",
    });
    value.controller.dispose();
  });

  test.each(["false", "rejected"] as const)(
    "fails Runtime state when gate release is %s",
    async (result) => {
      const value = sampleFixture({
        inspectSample: async (slot) => sampleInspect(slot, "gate"),
      });
      value.session.release = async (slot, source) => {
        value.releases.push({slot, source});
        if (result === "rejected") {
          throw Object.assign(new Error("release failed"), {code: "HOST_TIMEOUT"});
        }
        return false;
      };
      value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
      await settle();
      value.controller.keyUp({code: "KeyQ"});
      await settle();
      expect(value.actions.at(-1)).toEqual({
        type: "runtime-changed",
        phase: result === "rejected" ? "restart-required" : "failed",
        errorCode: result === "rejected"
          ? "HOST_TIMEOUT"
          : "HOST_STATE_INVALID",
      });
      value.controller.dispose();
    },
  );

  test.each([
    [
      "malformed",
      async (slot: number) => ({...sampleInspect(slot), extra: true}) as SampleInspect,
      "HOST_PROTOCOL_MISMATCH",
    ],
    [
      "failed",
      async (_slot: number) => {
        throw Object.assign(new Error("unavailable"), {code: "HOST_STATE_INVALID"});
      },
      "HOST_STATE_INVALID",
    ],
  ])("does not trigger when inspect is %s", async (_label, inspectSample, code) => {
    const value = sampleFixture({inspectSample});
    value.controller.keyDown({code: "KeyQ", repeat: false, target: document.body});
    await settle();
    expect(value.triggers).toEqual([]);
    expect(value.state().pressed.has(0)).toBe(false);
    expect(value.actions.at(-1)).toEqual({
      type: "runtime-changed",
      phase: "failed",
      errorCode: code,
    });
    value.controller.keyUp({code: "KeyQ"});
    value.controller.dispose();
  });

  test("does not retain pressed state when an assigned trigger is unavailable or fails", async () => {
    const unavailable = sampleFixture({
      inspectSample: async (slot) => sampleInspect(slot, "gate"),
    });
    unavailable.session.trigger = async () => false;
    expect(unavailable.controller.keyDown({
      code: "KeyQ",
      repeat: false,
      target: document.body,
    })).toBe(true);
    await settle();
    expect(unavailable.state().pressed.has(0)).toBe(false);
    unavailable.controller.keyUp({code: "KeyQ"});
    await settle();
    expect(unavailable.releases).toEqual([]);
    unavailable.controller.dispose();

    const failed = sampleFixture();
    failed.session.trigger = async () => {
      throw Object.assign(new Error("unavailable"), {code: "HOST_STATE_INVALID"});
    };
    expect(failed.controller.keyDown({
      code: "KeyQ",
      repeat: false,
      target: document.body,
    })).toBe(true);
    await settle();
    expect(failed.state().pressed.has(0)).toBe(false);
    expect(failed.actions.at(-1)).toEqual({
      type: "runtime-changed",
      phase: "failed",
      errorCode: "HOST_STATE_INVALID",
    });
    failed.controller.keyUp({code: "KeyQ"});
    failed.controller.dispose();
  });

  test("maps physical keys through the current Bank and follows admission/outcome", async () => {
    const value = fixture();
    let bank: 0 | 1 | 2 | 3 = 2;
    value.selectBank(bank);
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => bank,
      isAssigned: (slot) => [32, 39, 40, 47, 48].includes(slot),
      dispatch: value.dispatch,
    });

    expect(controller.keyDown({code: "KeyQ", repeat: false, target: document.body})).toBe(true);
    expect(controller.keyDown({code: "KeyQ", repeat: true, target: document.body})).toBe(false);
    expect(controller.keyDown({code: "KeyW", repeat: false, target: document.body})).toBe(false);
    expect(controller.keyDown({code: "KeyQ", repeat: false, target: document.createElement("input")})).toBe(false);
    await settle();
    expect(value.triggers).toEqual([{slot: 32, velocity: 100, source: "keyboard"}]);
    expect(value.state().pressed.get(32)).toBe("admitted");

    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    expect(value.state().pressed.get(32)).toBe("started");
    expect(controller.keyUp({code: "KeyQ"})).toBe(true);
    expect(value.state().pressed.has(32)).toBe(false);

    for (const [code, slot] of [
      ["KeyI", 39],
      ["KeyA", 40],
      ["KeyK", 47],
    ] as const) {
      expect(controller.keyDown({code, repeat: false, target: document.body})).toBe(true);
      await settle();
      expect(value.triggers.at(-1)?.slot).toBe(slot);
      expect(controller.keyUp({code})).toBe(true);
    }

    bank = 3;
    value.selectBank(bank);
    expect(controller.keyDown({code: "KeyQ", repeat: false, target: document.body})).toBe(true);
    await settle();
    expect(value.triggers.at(-1)?.slot).toBe(48);
    controller.dispose();
  });

  test("suppresses compatibility mouse and never re-presses after a late outcome", async () => {
    const value = fixture();
    const target = document.createElement("button");
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => 0,
      isAssigned: (slot) => slot === 0,
      dispatch: value.dispatch,
      now: () => 10,
    });
    const pointer = {
      type: "pointerdown",
      isPrimary: true,
      button: 0,
      pointerId: 7,
      clientX: 20,
      clientY: 30,
      target,
    };
    expect(controller.pointerDown(pointer, 0)).toBe(true);
    expect(controller.pointerDown({...pointer, type: "mousedown"}, 0)).toBe(false);
    expect(controller.pointerUp({pointerId: 7}, 0)).toBe(true);
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.state().pressed.has(0)).toBe(false);
    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    expect(value.state().pressed.has(0)).toBe(false);
    controller.dispose();
  });

  test("maps MIDI 36..51 on every channel to the selected Bank and removes listeners", async () => {
    const value = fixture();
    const input = fakeMidiInput();
    const access = fakeMidiAccess(input);
    let bank: 0 | 1 | 2 | 3 = 1;
    value.selectBank(bank);
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => bank,
      isAssigned: (slot) => slot === 16 || slot === 32,
      dispatch: value.dispatch,
      requestMIDIAccess: async () => access,
    });
    expect(await controller.enableMidi()).toBe(true);
    input.emit([0x99, 36, 73]);
    input.emit([0x99, 52, 73]);
    await settle();
    expect(value.triggers).toEqual([{slot: 16, velocity: 73, source: "midi"}]);
    expect(value.state().pressed.get(16)).toBe("admitted");
    input.emit([0x89, 36, 64]);
    expect(value.state().pressed.has(16)).toBe(false);

    bank = 2;
    value.selectBank(bank);
    input.emit([0x90, 36, 91]);
    await settle();
    expect(value.triggers.at(-1)).toEqual({slot: 32, velocity: 91, source: "midi"});
    window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: true}));
    expect(value.state().pressed.size).toBe(0);
    expect(input.listenerCount()).toBe(1);
    expect(access.listenerCount()).toBe(1);
    input.emit([0x90, 36, 92]);
    await settle();
    expect(value.triggers.at(-1)).toEqual({slot: 32, velocity: 92, source: "midi"});

    window.dispatchEvent(new PageTransitionEvent("pagehide", {persisted: false}));
    expect(input.listenerCount()).toBe(0);
    expect(access.listenerCount()).toBe(0);
    controller.dispose();
    expect(input.listenerCount()).toBe(0);
    expect(access.listenerCount()).toBe(0);
  });

  test("reports MIDI permission rejection without creating a trigger", async () => {
    const value = fixture();
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => 0,
      isAssigned: () => true,
      dispatch: value.dispatch,
      requestMIDIAccess: async () => { throw new DOMException("denied", "NotAllowedError"); },
    });
    expect(await controller.enableMidi()).toBe(false);
    expect(value.triggers).toEqual([]);
    controller.dispose();
  });

  test("reconciles a synchronous 16-key burst including capacity outcomes", async () => {
    const value = fixture();
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => 0,
      isAssigned: () => true,
      dispatch: value.dispatch,
    });
    const codes = [
      "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
      "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
    ];
    expect(Object.keys(DEFAULT_KEYBOARD_MAPPING)).toEqual(codes);
    for (const code of codes) {
      expect(controller.keyDown({code, repeat: false, target: document.body})).toBe(true);
    }
    await settle();
    expect(value.triggers).toHaveLength(16);
    expect(value.triggers.map(({slot}) => slot)).toEqual(
      Object.values(DEFAULT_KEYBOARD_MAPPING),
    );
    expect(value.state().pressed.size).toBe(16);
    for (let sequence = 1; sequence <= 16; sequence += 1) {
      value.outcome({
        sequence,
        outcome: sequence === 16 ? "voice_capacity" : "voice_started",
        runtimeFrame: 128,
      });
    }
    expect(value.state().pressed.get(15)).toBe("capacity");
    controller.clearPressed();
    expect(value.state().pressed.size).toBe(0);
    controller.dispose();
  });

  test("global keyboard, blur, and disposal own exactly one listener lifecycle", async () => {
    const value = fixture();
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => 0,
      isAssigned: (slot) => slot === 0,
      dispatch: value.dispatch,
    });
    window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyQ"}));
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.state().pressed.get(0)).toBe("admitted");
    window.dispatchEvent(new Event("blur"));
    expect(value.state().pressed.size).toBe(0);
    controller.dispose();
    window.dispatchEvent(new KeyboardEvent("keyup", {code: "KeyQ"}));
    window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyQ"}));
    await settle();
    expect(value.triggers).toHaveLength(1);
  });

  test("hidden visibility and blur clear a held key idempotently before later admission", async () => {
    const value = fixture();
    const originalVisibility = Object.getOwnPropertyDescriptor(
      document,
      "visibilityState",
    );
    const setVisibility = (visibilityState: DocumentVisibilityState) => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: visibilityState,
      });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => 0,
      isAssigned: (slot) => slot === 0,
      dispatch: value.dispatch,
    });
    try {
      window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyQ"}));
      await settle();
      expect(value.triggers).toHaveLength(1);
      expect(value.state().pressed.get(0)).toBe("admitted");

      setVisibility("hidden");
      expect(value.state().pressed.size).toBe(0);
      setVisibility("hidden");
      window.dispatchEvent(new Event("blur"));
      window.dispatchEvent(new Event("blur"));
      expect(value.state().pressed.size).toBe(0);

      setVisibility("visible");
      window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyQ"}));
      await settle();
      expect(value.triggers).toHaveLength(2);
      expect(value.state().pressed.get(0)).toBe("admitted");
    } finally {
      controller.dispose();
      if (originalVisibility) {
        Object.defineProperty(document, "visibilityState", originalVisibility);
      }
    }
  });
});
