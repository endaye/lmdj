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
  isAvailable = () => true,
}) {
  requireTrigger(trigger);
  requireVelocity(velocity);
  if (typeof isAvailable !== "function") {
    throw new TypeError("Pointer availability must be an injected function");
  }
  let suppressCompatibilityMouse = false;

  function canTrigger(slot, options) {
    return (
      isFlatSlot(slot) &&
      options?.disabled !== true &&
      isAvailable(slot) === true
    );
  }

  function pointerDown(event, flatSlot, options = {}) {
    if (
      event?.isPrimary !== true ||
      event?.button !== 0 ||
      !canTrigger(flatSlot, options)
    ) {
      return false;
    }
    suppressCompatibilityMouse = true;
    trigger(flatSlot, velocity);
    return true;
  }

  function mouseDown(event, flatSlot, options = {}) {
    if (event?.button !== 0) {
      return false;
    }
    if (suppressCompatibilityMouse) {
      suppressCompatibilityMouse = false;
      return false;
    }
    if (!canTrigger(flatSlot, options)) {
      return false;
    }
    trigger(flatSlot, velocity);
    return true;
  }

  return Object.freeze({
    pointerDown,
    mouseDown,
    clearPressed() {
      suppressCompatibilityMouse = false;
    },
  });
}

export function createKeyboardAdapter({
  trigger,
  mapping,
  velocity,
  editable = isEditableTarget,
}) {
  requireTrigger(trigger);
  requireVelocity(velocity);
  if (typeof editable !== "function") {
    throw new TypeError("Keyboard editable detection must be a function");
  }
  const entries = mapping instanceof Map ? [...mapping] : Object.entries(mapping ?? {});
  const codeToSlot = new Map(entries);
  for (const [code, slot] of codeToSlot) {
    if (typeof code !== "string" || !isFlatSlot(slot)) {
      throw new TypeError("Keyboard mappings require code to flat slot entries");
    }
  }
  const pressed = new Set();

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
    pressed.add(code);
    trigger(codeToSlot.get(code), velocity);
    return true;
  }

  function keyUp(event) {
    return pressed.delete(event?.code);
  }

  function clearPressed() {
    const count = pressed.size;
    pressed.clear();
    return count;
  }

  return Object.freeze({ keyDown, keyUp, clearPressed });
}

export function createMidiAdapter({
  trigger,
  requestMIDIAccess,
  notify,
  noteStart,
  slotStart,
  slotCount,
}) {
  requireTrigger(trigger);
  if (
    typeof requestMIDIAccess !== "function" ||
    typeof notify !== "function"
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
    slotStart + slotCount > 64
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

  function pressedFor(input) {
    let pressed = pressedByInput.get(input);
    if (!pressed) {
      pressed = new Set();
      pressedByInput.set(input, pressed);
    }
    return pressed;
  }

  function message(event, input) {
    const data = event?.data;
    if (!data || data.length < 3) {
      return false;
    }
    const status = data[0] & 0xf0;
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
    if (status === 0x80 || (status === 0x90 && velocity === 0)) {
      pressed.delete(note);
      return false;
    }
    if (status !== 0x90) {
      return false;
    }
    const offset = note - noteStart;
    if (offset < 0 || offset >= slotCount) {
      return false;
    }
    pressed.add(note);
    trigger(slotStart + offset, velocity);
    return true;
  }

  function attachInput(input) {
    if (!input || input.type !== "input" || connectedInputs.has(input)) {
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
    const lostPressedNotes = pressedByInput.get(input)?.size ?? 0;
    pressedByInput.delete(input);
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
    pressedByInput.clear();
    messageHandlers.clear();
    access = null;
  }

  return Object.freeze({
    requestPermission,
    message,
    stateChange,
    diagnostics,
    dispose,
  });
}
