import assert from "node:assert/strict";
import test from "node:test";

import {
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
} from "../src/input_adapters.mjs";

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
  assert.deepEqual(calls, [[17, 96]]);
});

test("Pointer suppresses the compatibility mouse activation for a pointer sequence", () => {
  const calls = [];
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
  });
  pointer.pointerDown({ isPrimary: true, button: 0 }, 4);
  assert.equal(pointer.mouseDown({ button: 0 }, 4), false);
  assert.equal(pointer.mouseDown({ button: 0 }, 4), true);
  assert.deepEqual(calls, [
    [4, 100],
    [4, 100],
  ]);
});

test("Pointer rejects disabled, unavailable, and out-of-range Pads", () => {
  const calls = [];
  const pointer = createPointerAdapter({
    trigger: (...args) => calls.push(args),
    velocity: 100,
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
    mapping: { KeyA: 3 },
    velocity: 91,
  });
  assert.equal(
    keyboard.keyDown({ code: "KeyA", key: "q", repeat: false }),
    true,
  );
  assert.equal(
    keyboard.keyDown({ code: "KeyA", key: "a", repeat: true }),
    false,
  );
  assert.deepEqual(calls, [[3, 91]]);
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
    [3, 91],
    [3, 91],
    [3, 91],
  ]);
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
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => fakeMidiAccess(),
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 28,
  });
  await midi.requestPermission();
  const input = fakeMidiInput();
  assert.equal(midi.message({ data: Uint8Array.from([0x90, 36, 0]) }, input), false);
  assert.deepEqual(calls, []);
  assert.equal(midi.diagnostics().pressed_note_count, 0);
});

test("Web MIDI preserves Note On velocity in exactly one flat Trigger", async () => {
  const calls = [];
  const midi = createMidiAdapter({
    trigger: (...args) => calls.push(args),
    requestMIDIAccess: async () => fakeMidiAccess(),
    notify: () => {},
    noteStart: 36,
    slotStart: 8,
    slotCount: 28,
  });
  await midi.requestPermission();
  const input = fakeMidiInput();
  assert.equal(midi.message({ data: Uint8Array.from([0x90, 40, 73]) }, input), true);
  assert.deepEqual(calls, [[12, 73]]);
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
  assert.deepEqual(calls, [[0, 64]]);
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
