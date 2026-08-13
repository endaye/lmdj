import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_KEYBOARD_MAPPING,
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
  flattenPadSlot,
} from "../web/input_adapters.mjs";

test("exports one frozen default keyboard mapping", () => {
  assert.equal(Object.isFrozen(DEFAULT_KEYBOARD_MAPPING), true);
  assert.deepEqual(DEFAULT_KEYBOARD_MAPPING, {
    KeyQ: 0,
    KeyW: 1,
    KeyE: 2,
    KeyR: 3,
    KeyT: 4,
    KeyY: 5,
    KeyU: 6,
    KeyI: 7,
    KeyA: 8,
    KeyS: 9,
    KeyD: 10,
    KeyF: 11,
    KeyG: 12,
    KeyH: 13,
    KeyJ: 14,
    KeyK: 15,
  });
});

test("flattens a Project Pad address at the input boundary", () => {
  assert.equal(flattenPadSlot({bank: 3, pad: 15}), 63);
  assert.throws(() => flattenPadSlot({bank: -1, pad: 0}), RangeError);
  assert.throws(() => flattenPadSlot({bank: 0, pad: 16}), RangeError);
});

function fakeMidiInput(sensitive = {}) {
  const listeners = new Map();
  return {
    type: "input",
    state: "connected",
    name: "Private Controller",
    manufacturer: "Private Manufacturer",
    id: "stable-private-id",
    serial: "private-serial",
    ...sensitive,
    addEventListener(event, callback) {
      listeners.set(event, callback);
    },
    removeEventListener(event, callback) {
      if (listeners.get(event) === callback) {
        listeners.delete(event);
      }
    },
    emit(event, value) {
      listeners.get(event)?.(value);
    },
  };
}

function fakeMidiAccess(inputs = []) {
  const listeners = new Map();
  return {
    inputs: new Map(inputs.map((input, index) => [String(index), input])),
    addEventListener(event, callback) {
      listeners.set(event, callback);
    },
    removeEventListener(event, callback) {
      if (listeners.get(event) === callback) {
        listeners.delete(event);
      }
    },
    emit(event, value) {
      listeners.get(event)?.(value);
    },
  };
}

test("Pointer primary activation emits exactly one flat Trigger", () => {
  const calls = [];
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 96,
    now: () => 0,
  });
  assert.equal(
    pointer.pointerDown({ isPrimary: true, button: 0 }, 17),
    true,
  );
  assert.equal(
    pointer.pointerDown({ isPrimary: false, button: 0 }, 17),
    false,
  );
  assert.equal(pointer.pointerDown({ isPrimary: true, button: 1 }, 17), false);
  assert.deepEqual(calls, [[17, 96, "pointer"]]);
});

test("Pointer suppresses the compatibility mouse activation for a pointer sequence", () => {
  const calls = [];
  const target = {};
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
    now: () => 10,
    compatibilityWindowMs: 500,
  });
  const correlated = { button: 0, clientX: 20, clientY: 30, target };
  pointer.pointerDown(
    { ...correlated, isPrimary: true, pointerId: 7 },
    4,
  );
  assert.equal(pointer.mouseDown(correlated, 4), false);
  assert.equal(pointer.mouseDown(correlated, 4), true);
  assert.deepEqual(calls, [
    [4, 100, "pointer"],
    [4, 100, "pointer"],
  ]);
});

test("Pointer suppresses Chromium rounded compatibility mouse coordinates", () => {
  const calls = [];
  const target = {};
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
    now: () => 10,
    compatibilityWindowMs: 500,
  });
  pointer.pointerDown({
    isPrimary: true,
    button: 0,
    pointerId: 7,
    clientX: 160.5,
    clientY: 309.5,
    target,
  }, 4);

  assert.equal(pointer.mouseDown({
    button: 0,
    clientX: 160,
    clientY: 309,
    target,
  }, 4), false);
  assert.deepEqual(calls, [[4, 100, "pointer"]]);
});

test("Pointer cancellation and marker expiry never suppress a later genuine mouse", () => {
  const calls = [];
  const target = {};
  let monotonicNow = 0;
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
    now: () => monotonicNow,
    compatibilityWindowMs: 50,
  });
  const activation = {
    isPrimary: true,
    button: 0,
    pointerId: 9,
    clientX: 1,
    clientY: 2,
    target,
  };

  pointer.pointerDown(activation, 4);
  pointer.pointerCancel({ pointerId: 9 });
  assert.equal(pointer.mouseDown(activation, 4), true);

  pointer.pointerDown(activation, 4);
  monotonicNow = 51;
  assert.equal(pointer.mouseDown(activation, 4), true);

  pointer.pointerDown(activation, 4);
  pointer.clearPressed();
  assert.equal(pointer.mouseDown(activation, 4), true);
  assert.deepEqual(calls, [
    [4, 100, "pointer"],
    [4, 100, "pointer"],
    [4, 100, "pointer"],
    [4, 100, "pointer"],
    [4, 100, "pointer"],
    [4, 100, "pointer"],
  ]);
});

test("Pointer marker mismatch does not suppress an independent mouse activation", () => {
  const calls = [];
  const pointerTarget = {};
  const mouseTarget = {};
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
    now: () => 0,
    compatibilityWindowMs: 500,
  });
  pointer.pointerDown(
    {
      isPrimary: true,
      button: 0,
      pointerId: 3,
      clientX: 10,
      clientY: 20,
      target: pointerTarget,
    },
    4,
  );
  assert.equal(
    pointer.mouseDown(
      { button: 0, clientX: 11, clientY: 20, target: mouseTarget },
      5,
    ),
    true,
  );
  assert.deepEqual(calls, [
    [4, 100, "pointer"],
    [5, 100, "pointer"],
  ]);
});

test("Pointer rejects disabled, unavailable, and out-of-range Pads", () => {
  const calls = [];
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
    now: () => 0,
    isAvailable: (slot) => slot !== 9,
  });
  assert.equal(pointer.pointerDown({ isPrimary: true, button: 0 }, 8, { disabled: true }), false);
  assert.equal(pointer.pointerDown({ isPrimary: true, button: 0 }, 9), false);
  assert.equal(pointer.pointerDown({ isPrimary: true, button: 0 }, 64), false);
  assert.deepEqual(calls, []);
});

test("Keyboard maps physical code, ignores repeat, and preserves fixed velocity", () => {
  const calls = [];
  const keyboard = createKeyboardAdapter({
    trigger: (...args) => calls.push(args),
    mapping: { KeyA: 3, KeyB: 4 },
    velocity: 91,
  });
  assert.equal(
    keyboard.keyDown({ code: "KeyA", key: "q", repeat: false }),
    true,
  );
  assert.equal(
    keyboard.keyDown({ code: "KeyB", key: "b", repeat: true }),
    false,
  );
  assert.deepEqual(calls, [[3, 91, "keyboard"]]);
});

test("Keyboard disables shortcuts in editable focus", () => {
  const calls = [];
  const keyboard = createKeyboardAdapter({
    trigger: (...args) => calls.push(args),
    mapping: { KeyA: 3 },
    velocity: 91,
  });
  for (const target of [
    { tagName: "INPUT" },
    { tagName: "TEXTAREA" },
    { tagName: "SELECT" },
    { isContentEditable: true },
  ]) {
    assert.equal(
      keyboard.keyDown({ code: "KeyA", repeat: false, target }),
      false,
    );
  }
  assert.deepEqual(calls, []);
});

test("Keyboard keyup and lifecycle cleanup clear pressed state", () => {
  const calls = [];
  const keyboard = createKeyboardAdapter({
    trigger: (...args) => calls.push(args),
    mapping: { KeyA: 3 },
    velocity: 91,
  });
  keyboard.keyDown({ code: "KeyA", repeat: false });
  assert.equal(keyboard.keyDown({ code: "KeyA", repeat: false }), false);
  keyboard.keyUp({ code: "KeyA" });
  assert.equal(keyboard.keyDown({ code: "KeyA", repeat: false }), true);
  keyboard.clearPressed();
  assert.equal(keyboard.keyDown({ code: "KeyA", repeat: false }), true);
  assert.deepEqual(calls, [
    [3, 91, "keyboard"],
    [3, 91, "keyboard"],
    [3, 91, "keyboard"],
  ]);
});

test("Keyboard resolves a local mapping at keydown and releases the resolved slot", () => {
  const calls = [];
  const releases = [];
  let bank = 2;
  const keyboard = createKeyboardAdapter({
    trigger: (...args) => calls.push(args),
    mapping: { KeyA: 0 },
    resolveSlot: (localSlot) => bank * 16 + localSlot,
    velocity: 100,
    onRelease: (slot, source) => releases.push([slot, source]),
  });
  keyboard.keyDown({ code: "KeyA", repeat: false });
  bank = 3;
  keyboard.keyUp({ code: "KeyA" });
  assert.deepEqual(calls, [[32, 100, "keyboard"]]);
  assert.deepEqual(releases, [[32, "keyboard"]]);
});

test("Web MIDI permission is explicit and always requests sysex false", async () => {
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const requests = [];
  const midi = createMidiAdapter({
    trigger: () => {},
    requestMIDIAccess: async (options) => {
      requests.push(options);
      return access;
    },
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  assert.deepEqual(requests, []);
  await midi.requestPermission();
  assert.deepEqual(requests, [{ sysex: false }]);
  assert.equal(midi.diagnostics().permission, "granted");
});

test("Web MIDI treats velocity-zero Note On as Note Off", async () => {
  const calls = [];
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => access,
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  await midi.requestPermission();
  assert.equal(midi.message({ data: Uint8Array.from([0x90, 36, 81]) }, input), true);
  assert.equal(midi.diagnostics().pressed_note_count, 1);
  assert.equal(midi.message({ data: Uint8Array.from([0x90, 36, 0]) }, input), false);
  assert.deepEqual(calls, [[0, 81, "midi"]]);
  assert.equal(midi.diagnostics().pressed_note_count, 0);
});

test("Web MIDI preserves Note On velocity in exactly one flat Trigger", async () => {
  const calls = [];
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => access,
    notify: () => {},
    noteStart: 36,
    slotStart: 8,
    slotCount: 28,
  });
  await midi.requestPermission();
  assert.equal(midi.message({ data: Uint8Array.from([0x90, 40, 73]) }, input), true);
  assert.deepEqual(calls, [[12, 73, "midi"]]);
});

test("Web MIDI resolves the current Bank, filters channel, and releases the admitted slot", async () => {
  const calls = [];
  const releases = [];
  let bank = 1;
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => access,
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 16,
    channel: 0,
    resolveSlot: (localSlot) => bank * 16 + localSlot,
    onRelease: (slot, source) => releases.push([slot, source]),
  });
  await midi.requestPermission();
  input.emit("midimessage", { data: Uint8Array.from([0x90, 36, 72]) });
  input.emit("midimessage", { data: Uint8Array.from([0x91, 36, 72]) });
  bank = 3;
  input.emit("midimessage", { data: Uint8Array.from([0x90, 36, 0]) });
  assert.deepEqual(calls, [[16, 72, "midi"]]);
  assert.deepEqual(releases, [[16, "midi"]]);
});

test("Web MIDI ignores messages before permission, from unknown inputs, and after disconnect", async () => {
  const calls = [];
  const input = fakeMidiInput();
  const unknown = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => access,
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  const noteOn = { data: Uint8Array.from([0x90, 36, 90]) };

  assert.equal(midi.message(noteOn, input), false);
  await midi.requestPermission();
  assert.equal(midi.message(noteOn, unknown), false);
  assert.equal(midi.message(noteOn, input), true);
  access.emit("statechange", {
    port: Object.assign(input, { state: "disconnected" }),
  });
  assert.equal(midi.message(noteOn, input), false);
  assert.deepEqual(calls, [[0, 90, "midi"]]);
  assert.equal(midi.diagnostics().pressed_note_count, 0);
});

test("Web MIDI disconnect clears pressed state without synthesizing triggers", async () => {
  const calls = [];
  const notifications = [];
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => access,
    notify: (event, payload) => notifications.push({ event, payload }),
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  await midi.requestPermission();
  input.emit("midimessage", { data: Uint8Array.from([0x90, 36, 64]) });
  assert.equal(midi.diagnostics().pressed_note_count, 1);
  access.emit("statechange", {
    port: Object.assign(input, { state: "disconnected" }),
  });
  assert.equal(midi.diagnostics().pressed_note_count, 0);
  assert.deepEqual(calls, [[0, 64, "midi"]]);
  assert.deepEqual(
    notifications.map(({ event }) => event),
    ["midi.connected", "midi.disconnected"],
  );
});

test("Web MIDI diagnostics and notifications redact device identity and raw messages", async () => {
  const reports = [];
  const input = fakeMidiInput();
  const access = fakeMidiAccess([input]);
  const midi = createMidiAdapter({
    trigger: () => {},
    requestMIDIAccess: async () => access,
    notify: (event, payload) => reports.push({ event, payload }),
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  await midi.requestPermission();
  input.emit("midimessage", { data: Uint8Array.from([0x90, 36, 99]) });
  const serialized = JSON.stringify({ reports, diagnostics: midi.diagnostics() });
  for (const secret of [
    input.name,
    input.manufacturer,
    input.id,
    input.serial,
    "144,36,99",
  ]) {
    assert.equal(serialized.includes(secret), false, secret);
  }
  assert.deepEqual(midi.diagnostics(), {
    permission: "granted",
    connected_input_count: 1,
    pressed_note_count: 1,
  });
});
