import {describe, expect, test} from "vitest";
import {DEFAULT_KEYBOARD_MAPPING} from "@lmdj/web-runtime-platform/input_adapters.mjs";

import {createCreatorInputController} from "../src/runtime/input_controller";
import type {
  CreatorRuntimeSession,
  RuntimeHostState,
  RuntimeOutcome,
} from "../src/runtime/runtime_types";
import {
  creatorReducer,
  initialCreatorState,
  type CreatorAction,
  type CreatorState,
} from "../src/state/creator_state";

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
  let state: CreatorState = initialCreatorState;
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
      product_build: "1.0.16.9",
      host_id: "creator-web",
      host_version: "1.0.6",
      platform_version: "0.1.6",
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
    outcome(outcome: RuntimeOutcome) {
      for (const listener of outcomeListeners) listener(outcome);
    },
  };
}

async function settle() {
  await Promise.resolve();
  await Promise.resolve();
}

describe("Creator input controller", () => {
  test("maps physical keys through the current Bank and follows admission/outcome", async () => {
    const value = fixture();
    let bank: 0 | 1 | 2 | 3 = 2;
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => bank,
      isAssigned: (slot) => slot === 32 || slot === 48,
      dispatch: value.dispatch,
    });

    expect(controller.keyDown({code: "KeyA", repeat: false, target: document.body})).toBe(true);
    expect(controller.keyDown({code: "KeyA", repeat: true, target: document.body})).toBe(false);
    expect(controller.keyDown({code: "KeyS", repeat: false, target: document.body})).toBe(false);
    expect(controller.keyDown({code: "KeyA", repeat: false, target: document.createElement("input")})).toBe(false);
    await settle();
    expect(value.triggers).toEqual([{slot: 32, velocity: 100, source: "keyboard"}]);
    expect(value.state().pressed.get(32)).toBe("admitted");

    value.outcome({sequence: 1, outcome: "voice_started", runtimeFrame: 128});
    expect(value.state().pressed.get(32)).toBe("started");
    expect(controller.keyUp({code: "KeyA"})).toBe(true);
    expect(value.state().pressed.has(32)).toBe(false);

    bank = 3;
    expect(controller.keyDown({code: "KeyA", repeat: false, target: document.body})).toBe(true);
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

  test("maps MIDI 36..51 on channel 1 to the selected Bank and removes listeners", async () => {
    const value = fixture();
    const input = fakeMidiInput();
    const access = fakeMidiAccess(input);
    let bank: 0 | 1 | 2 | 3 = 1;
    const controller = createCreatorInputController({
      session: value.session,
      getActiveBank: () => bank,
      isAssigned: (slot) => slot === 16 || slot === 32,
      dispatch: value.dispatch,
      requestMIDIAccess: async () => access,
    });
    expect(await controller.enableMidi()).toBe(true);
    input.emit([0x90, 36, 73]);
    input.emit([0x91, 36, 73]);
    input.emit([0x90, 52, 73]);
    await settle();
    expect(value.triggers).toEqual([{slot: 16, velocity: 73, source: "midi"}]);
    expect(value.state().pressed.get(16)).toBe("admitted");
    input.emit([0x90, 36, 0]);
    expect(value.state().pressed.has(16)).toBe(false);

    bank = 2;
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
      "KeyA", "KeyS", "KeyD", "KeyF", "KeyG", "KeyH", "KeyJ", "KeyK",
      "KeyQ", "KeyW", "KeyE", "KeyR", "KeyT", "KeyY", "KeyU", "KeyI",
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
    window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyA"}));
    await settle();
    expect(value.triggers).toHaveLength(1);
    expect(value.state().pressed.get(0)).toBe("admitted");
    window.dispatchEvent(new Event("blur"));
    expect(value.state().pressed.size).toBe(0);
    controller.dispose();
    window.dispatchEvent(new KeyboardEvent("keyup", {code: "KeyA"}));
    window.dispatchEvent(new KeyboardEvent("keydown", {code: "KeyA"}));
    await settle();
    expect(value.triggers).toHaveLength(1);
  });
});
