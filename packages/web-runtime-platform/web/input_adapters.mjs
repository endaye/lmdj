const userGestureTokens = new WeakSet();
const acceptAnySlot = (_slot) => true;
const ignoreRelease = (_slot, _source, _gestureKey) => {};
const ignoreCancel = (_slot, _source, _gestureKey) => {};
/** @type {number | null} */
const allMidiChannels = null;

function createGestureKey() {
  return Object.freeze({});
}

export const DEFAULT_KEYBOARD_MAPPING = Object.freeze({
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


export function createUserGestureToken(event) {
  if (event === null || typeof event !== "object" || event.isTrusted !== true) {
    throw new TypeError("Audio activation requires a trusted browser event");
  }
  const token = Object.freeze({kind: "lmdj.web-runtime.user-gesture"});
  userGestureTokens.add(token);
  return token;
}

Object.defineProperty(createUserGestureToken, "consume", {
  value(token) {
    return (
      token?.kind === "lmdj.web-runtime.user-gesture" &&
      userGestureTokens.delete(token)
    );
  },
});

export function flattenPadSlot({bank, pad}) {
  if (
    !Number.isInteger(bank) ||
    !Number.isInteger(pad) ||
    bank < 0 ||
    bank > 3 ||
    pad < 0 ||
    pad > 15
  ) {
    throw new RangeError("Project Pad address must be bank 0..3 and pad 0..15");
  }
  return bank * 16 + pad;
}


function requireTrigger(trigger) {
  if (typeof trigger !== "function") {
    throw new TypeError("A Trigger sink must be injected");
  }
}

function requireVelocity(velocity) {
  if (!Number.isInteger(velocity) || velocity < 1 || velocity > 127) {
    throw new RangeError("velocity must be an integer in 1..127");
  }
}

function isFlatSlot(slot) {
  return Number.isInteger(slot) && slot >= 0 && slot <= 63;
}

function isEditableTarget(target) {
  if (!target || typeof target !== "object") {
    return false;
  }
  if (target.isContentEditable === true) {
    return true;
  }
  const tagName =
    typeof target.tagName === "string" ? target.tagName.toUpperCase() : "";
  if (["INPUT", "TEXTAREA", "SELECT"].includes(tagName)) {
    return true;
  }
  return (
    typeof target.closest === "function" &&
    target.closest("input, textarea, select, [contenteditable='true']") !== null
  );
}

export function createPointerAdapter({
  trigger,
  velocity,
  isAvailable = acceptAnySlot,
  now,
  compatibilityWindowMs = 500,
  onPressedChange = () => {},
  onRelease = ignoreRelease,
  onCancel = ignoreCancel,
}) {
  requireTrigger(trigger);
  requireVelocity(velocity);
  if (typeof isAvailable !== "function") {
    throw new TypeError("Pointer availability must be an injected function");
  }
  if (
    typeof now !== "function" ||
    !Number.isFinite(compatibilityWindowMs) ||
    compatibilityWindowMs < 0
  ) {
    throw new TypeError("Pointer correlation requires an injected monotonic clock");
  }
  if (
    typeof onPressedChange !== "function" ||
    typeof onRelease !== "function" ||
    typeof onCancel !== "function"
  ) {
    throw new TypeError("Pointer pressed-state notification must be a function");
  }
  let compatibilityMarker = null;
  const pressed = new Set();
  const pointerSlots = new Map();
  const legacyPointers = [];
  const mouseGestures = [];
  const activeGestures = new Set();

  function publishPressed() {
    onPressedChange(Object.freeze([...pressed]));
  }

  function canTrigger(slot, options) {
    return (
      isFlatSlot(slot) &&
      options?.disabled !== true &&
      isAvailable(slot) === true
    );
  }

  function beginGesture(kind, flatSlot, pointerId) {
    const gesture = Object.freeze({
      kind,
      flatSlot,
      gestureKey: createGestureKey(),
      pointerId,
    });
    activeGestures.add(gesture);
    pressed.add(flatSlot);
    if (kind === "pointer") {
      if (pointerId === undefined) legacyPointers.push(gesture);
      else pointerSlots.set(pointerId, gesture);
    } else {
      mouseGestures.push(gesture);
    }
    return gesture;
  }

  function removeGesture(gesture) {
    if (!activeGestures.delete(gesture)) return false;
    if (gesture.kind === "pointer") {
      if (gesture.pointerId === undefined) {
        const index = legacyPointers.indexOf(gesture);
        if (index !== -1) legacyPointers.splice(index, 1);
      } else if (pointerSlots.get(gesture.pointerId) === gesture) {
        pointerSlots.delete(gesture.pointerId);
      }
    } else {
      const index = mouseGestures.indexOf(gesture);
      if (index !== -1) mouseGestures.splice(index, 1);
    }
    if (![...activeGestures].some((candidate) =>
      candidate.flatSlot === gesture.flatSlot)) {
      pressed.delete(gesture.flatSlot);
    }
    return true;
  }

  function closeGesture(gesture, callback) {
    if (gesture === undefined || !removeGesture(gesture)) return false;
    callback(gesture.flatSlot, "pointer", gesture.gestureKey);
    publishPressed();
    return true;
  }

  function pointerDown(event, flatSlot, options = {}) {
    if (
      event?.isPrimary !== true ||
      event?.button !== 0 ||
      !canTrigger(flatSlot, options)
    ) {
      return false;
    }
    const repeatedGesture = pointerSlots.get(event.pointerId);
    if (repeatedGesture !== undefined) {
      closeGesture(repeatedGesture, onCancel);
    }
    const gesture = beginGesture("pointer", flatSlot, event.pointerId);
    compatibilityMarker = Object.freeze({
      pointerId: event.pointerId,
      flatSlot,
      gesture,
      target: event.target,
      clientX: event.clientX,
      clientY: event.clientY,
      expiresAt: now() + compatibilityWindowMs,
    });
    publishPressed();
    trigger(flatSlot, velocity, "pointer", gesture.gestureKey);
    return true;
  }

  function matchesCompatibilityMouse(event, flatSlot, marker) {
    return (
      now() <= marker.expiresAt &&
      flatSlot === marker.flatSlot &&
      event?.target === marker.target &&
      Math.abs(event?.clientX - marker.clientX) <= 1 &&
      Math.abs(event?.clientY - marker.clientY) <= 1
    );
  }

  function mouseDown(event, flatSlot, options = {}) {
    if (event?.button !== 0) {
      return false;
    }
    const marker = compatibilityMarker;
    compatibilityMarker = null;
    if (marker !== null && matchesCompatibilityMouse(event, flatSlot, marker)) {
      return false;
    }
    if (!canTrigger(flatSlot, options)) {
      return false;
    }
    const gesture = beginGesture("mouse", flatSlot);
    publishPressed();
    trigger(flatSlot, velocity, "pointer", gesture.gestureKey);
    return true;
  }

  function pointerUp(event, flatSlot) {
    const gesture = event?.pointerId === undefined
      ? legacyPointers.find((candidate) => candidate.flatSlot === flatSlot)
      : pointerSlots.get(event.pointerId);
    if (gesture?.flatSlot !== flatSlot) return false;
    if (compatibilityMarker?.gesture === gesture) compatibilityMarker = null;
    return closeGesture(gesture, onRelease);
  }

  function releasePointer(event) {
    const gesture = pointerSlots.get(event?.pointerId);
    if (gesture === undefined) return false;
    if (compatibilityMarker?.gesture === gesture) compatibilityMarker = null;
    return closeGesture(gesture, onRelease);
  }

  function releaseMouse(event) {
    if (event?.button !== undefined && event.button !== 0) {
      return false;
    }
    return closeGesture(mouseGestures[0], onRelease);
  }

  function pointerCancel(event) {
    let gesture = pointerSlots.get(event?.pointerId);
    if (gesture !== undefined) {
      if (compatibilityMarker?.gesture === gesture) compatibilityMarker = null;
    } else {
      if (
        compatibilityMarker === null ||
        (event?.pointerId !== undefined &&
          event.pointerId !== compatibilityMarker.pointerId)
      ) {
        return false;
      }
      gesture = compatibilityMarker.gesture;
      compatibilityMarker = null;
    }
    return closeGesture(gesture, onCancel);
  }

  return Object.freeze({
    pointerDown,
    mouseDown,
    pointerUp,
    releasePointer,
    releaseMouse,
    pointerCancel,
    clearPressed() {
      compatibilityMarker = null;
      pointerSlots.clear();
      legacyPointers.length = 0;
      mouseGestures.length = 0;
      const gestures = [...activeGestures];
      const count = pressed.size;
      for (const gesture of gestures) {
        onRelease(gesture.flatSlot, "pointer", gesture.gestureKey);
      }
      activeGestures.clear();
      pressed.clear();
      publishPressed();
      return count;
    },
    diagnostics() {
      return Object.freeze({ pressed_count: pressed.size });
    },
  });
}

export function createKeyboardAdapter({
  trigger,
  mapping,
  velocity,
  resolveSlot = (slot) => slot,
  isAvailable = acceptAnySlot,
  editable = isEditableTarget,
  onPressedChange = () => {},
  onRelease = ignoreRelease,
}) {
  requireTrigger(trigger);
  requireVelocity(velocity);
  if (
    typeof resolveSlot !== "function" ||
    typeof isAvailable !== "function" ||
    typeof editable !== "function"
  ) {
    throw new TypeError("Keyboard editable detection must be a function");
  }
  if (typeof onPressedChange !== "function" || typeof onRelease !== "function") {
    throw new TypeError("Keyboard pressed-state notification must be a function");
  }
  const entries = mapping instanceof Map ? [...mapping] : Object.entries(mapping ?? {});
  const codeToSlot = new Map(entries);
  for (const [code, slot] of codeToSlot) {
    if (typeof code !== "string" || !isFlatSlot(slot)) {
      throw new TypeError("Keyboard mappings require code to flat slot entries");
    }
  }
  const pressed = new Map();

  function keyDown(event) {
    const code = event?.code;
    if (
      typeof code !== "string" ||
      event?.repeat === true ||
      editable(event?.target) ||
      !codeToSlot.has(code) ||
      pressed.has(code)
    ) {
      return false;
    }
    const flatSlot = resolveSlot(codeToSlot.get(code));
    if (!isFlatSlot(flatSlot) || isAvailable(flatSlot) !== true) {
      return false;
    }
    const gesture = Object.freeze({flatSlot, gestureKey: createGestureKey()});
    pressed.set(code, gesture);
    onPressedChange(pressed.size);
    trigger(flatSlot, velocity, "keyboard", gesture.gestureKey);
    return true;
  }

  function keyUp(event) {
    const gesture = pressed.get(event?.code);
    if (gesture !== undefined) {
      pressed.delete(event?.code);
      onRelease(gesture.flatSlot, "keyboard", gesture.gestureKey);
      onPressedChange(pressed.size);
      return true;
    }
    return false;
  }

  function clearPressed() {
    const count = pressed.size;
    for (const gesture of pressed.values()) {
      onRelease(gesture.flatSlot, "keyboard", gesture.gestureKey);
    }
    pressed.clear();
    onPressedChange(0);
    return count;
  }

  return Object.freeze({
    keyDown,
    keyUp,
    clearPressed,
    diagnostics() {
      return Object.freeze({ pressed_count: pressed.size });
    },
  });
}

export function createMidiAdapter({
  trigger,
  requestMIDIAccess,
  notify,
  noteStart,
  slotStart,
  slotCount,
  channel = allMidiChannels,
  resolveSlot = (slot) => slot,
  isAvailable = acceptAnySlot,
  onPressedChange = () => {},
  onRelease = ignoreRelease,
}) {
  requireTrigger(trigger);
  if (
    typeof requestMIDIAccess !== "function" ||
    typeof notify !== "function" ||
    typeof resolveSlot !== "function" ||
    typeof isAvailable !== "function" ||
    typeof onPressedChange !== "function" ||
    typeof onRelease !== "function"
  ) {
    throw new TypeError("MIDI access and notification sinks must be injected");
  }
  if (
    !Number.isInteger(noteStart) ||
    noteStart < 0 ||
    noteStart > 127 ||
    !isFlatSlot(slotStart) ||
    !Number.isInteger(slotCount) ||
    slotCount < 1 ||
    noteStart + slotCount > 128 ||
    slotStart + slotCount > 64 ||
    !(channel === null || (Number.isInteger(channel) && channel >= 0 && channel <= 15))
  ) {
    throw new RangeError("MIDI mapping must be a valid contiguous note and slot range");
  }

  let permission = "prompt";
  let access = null;
  const connectedInputs = new Set();
  const pressedByInput = new Map();
  const messageHandlers = new Map();

  function diagnostics() {
    let pressedNoteCount = 0;
    for (const notes of pressedByInput.values()) {
      pressedNoteCount += notes.size;
    }
    return Object.freeze({
      permission,
      connected_input_count: connectedInputs.size,
      pressed_note_count: pressedNoteCount,
    });
  }

  function publishPressed() {
    onPressedChange(diagnostics().pressed_note_count);
  }

  function pressedFor(input) {
    let pressed = pressedByInput.get(input);
    if (!pressed) {
      pressed = new Map();
      pressedByInput.set(input, pressed);
    }
    return pressed;
  }

  function message(event, input) {
    if (permission !== "granted" || !connectedInputs.has(input)) {
      return false;
    }
    const data = event?.data;
    if (!data || data.length < 3) {
      return false;
    }
    const status = data[0] & 0xf0;
    const messageChannel = data[0] & 0x0f;
    const note = data[1];
    const velocity = data[2];
    if (
      !Number.isInteger(note) ||
      note < 0 ||
      note > 127 ||
      !Number.isInteger(velocity) ||
      velocity < 0 ||
      velocity > 127
    ) {
      return false;
    }
    const pressed = pressedFor(input);
    if (channel !== null && messageChannel !== channel) {
      return false;
    }
    if (status === 0x80 || (status === 0x90 && velocity === 0)) {
      const gesture = pressed.get(note);
      pressed.delete(note);
      if (gesture !== undefined) {
        onRelease(gesture.flatSlot, "midi", gesture.gestureKey);
      }
      publishPressed();
      return false;
    }
    if (status !== 0x90) {
      return false;
    }
    const offset = note - noteStart;
    if (offset < 0 || offset >= slotCount) {
      return false;
    }
    if (pressed.has(note)) {
      return false;
    }
    const flatSlot = resolveSlot(slotStart + offset);
    if (!isFlatSlot(flatSlot) || isAvailable(flatSlot) !== true) {
      return false;
    }
    const gesture = Object.freeze({flatSlot, gestureKey: createGestureKey()});
    pressed.set(note, gesture);
    publishPressed();
    trigger(flatSlot, velocity, "midi", gesture.gestureKey);
    return true;
  }

  function attachInput(input) {
    if (
      permission !== "granted" ||
      !input ||
      input.type !== "input" ||
      input.state !== "connected" ||
      connectedInputs.has(input)
    ) {
      return false;
    }
    connectedInputs.add(input);
    pressedFor(input);
    const handler = (event) => message(event, input);
    messageHandlers.set(input, handler);
    input.addEventListener?.("midimessage", handler);
    notify("midi.connected", {
      connected_input_count: connectedInputs.size,
    });
    return true;
  }

  function detachInput(input) {
    if (!connectedInputs.has(input)) {
      pressedByInput.delete(input);
      return false;
    }
    const handler = messageHandlers.get(input);
    input.removeEventListener?.("midimessage", handler);
    messageHandlers.delete(input);
    connectedInputs.delete(input);
    const pressed = pressedByInput.get(input);
    const lostPressedNotes = pressed?.size ?? 0;
    for (const gesture of pressed?.values() ?? []) {
      onRelease(gesture.flatSlot, "midi", gesture.gestureKey);
    }
    pressedByInput.delete(input);
    publishPressed();
    notify("midi.disconnected", {
      connected_input_count: connectedInputs.size,
      lost_pressed_note_count: lostPressedNotes,
    });
    return true;
  }

  function stateChange(event) {
    const input = event?.port;
    if (!input || input.type !== "input") {
      return false;
    }
    return input.state === "disconnected"
      ? detachInput(input)
      : attachInput(input);
  }

  async function requestPermission() {
    if (access !== null) {
      return access;
    }
    permission = "requesting";
    try {
      const grantedAccess = await requestMIDIAccess({ sysex: false });
      access = grantedAccess;
      permission = "granted";
      access.addEventListener?.("statechange", stateChange);
      for (const input of access.inputs?.values?.() ?? []) {
        attachInput(input);
      }
      return access;
    } catch {
      permission = "denied";
      notify("runtime.warning", { code: "MIDI_PERMISSION_DENIED" });
      throw new Error("MIDI permission denied");
    }
  }

  function dispose() {
    access?.removeEventListener?.("statechange", stateChange);
    for (const input of [...connectedInputs]) {
      const handler = messageHandlers.get(input);
      input.removeEventListener?.("midimessage", handler);
    }
    connectedInputs.clear();
    for (const pressed of pressedByInput.values()) {
      for (const gesture of pressed.values()) {
        onRelease(gesture.flatSlot, "midi", gesture.gestureKey);
      }
    }
    pressedByInput.clear();
    publishPressed();
    messageHandlers.clear();
    access = null;
  }

  return Object.freeze({
    requestPermission,
    message,
    stateChange,
    diagnostics,
    clearPressed() {
      let count = 0;
      for (const notes of pressedByInput.values()) {
        count += notes.size;
        for (const gesture of notes.values()) {
          onRelease(gesture.flatSlot, "midi", gesture.gestureKey);
        }
        notes.clear();
      }
      publishPressed();
      return count;
    },
    dispose,
  });
}
