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
  now,
  compatibilityWindowMs = 500,
  onPressedChange = () => {},
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
  if (typeof onPressedChange !== "function") {
    throw new TypeError("Pointer pressed-state notification must be a function");
  }
  let compatibilityMarker = null;
  const pressed = new Set();
  const pointerSlots = new Map();
  let mouseSlot = null;

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

  function pointerDown(event, flatSlot, options = {}) {
    if (
      event?.isPrimary !== true ||
      event?.button !== 0 ||
      !canTrigger(flatSlot, options)
    ) {
      return false;
    }
    compatibilityMarker = Object.freeze({
      pointerId: event.pointerId,
      flatSlot,
      target: event.target,
      clientX: event.clientX,
      clientY: event.clientY,
      expiresAt: now() + compatibilityWindowMs,
    });
    pressed.add(flatSlot);
    if (event.pointerId !== undefined) {
      pointerSlots.set(event.pointerId, flatSlot);
    }
    publishPressed();
    trigger(flatSlot, velocity);
    return true;
  }

  function matchesCompatibilityMouse(event, flatSlot, marker) {
    return (
      now() <= marker.expiresAt &&
      flatSlot === marker.flatSlot &&
      event?.target === marker.target &&
      event?.clientX === marker.clientX &&
      event?.clientY === marker.clientY
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
    pressed.add(flatSlot);
    mouseSlot = flatSlot;
    publishPressed();
    trigger(flatSlot, velocity);
    return true;
  }

  function pointerUp(_event, flatSlot) {
    for (const [pointerId, slot] of pointerSlots) {
      if (slot === flatSlot) {
        pointerSlots.delete(pointerId);
      }
    }
    if (mouseSlot === flatSlot) {
      mouseSlot = null;
    }
    const changed = pressed.delete(flatSlot);
    if (changed) {
      publishPressed();
    }
    return changed;
  }

  function releasePointer(event) {
    const flatSlot = pointerSlots.get(event?.pointerId);
    if (flatSlot === undefined) {
      return false;
    }
    pointerSlots.delete(event.pointerId);
    if (compatibilityMarker?.pointerId === event.pointerId) {
      compatibilityMarker = null;
    }
    return pointerUp(event, flatSlot);
  }

  function releaseMouse(event) {
    if (event?.button !== undefined && event.button !== 0) {
      return false;
    }
    if (mouseSlot === null) {
      return false;
    }
    const flatSlot = mouseSlot;
    mouseSlot = null;
    return pointerUp(event, flatSlot);
  }

  function pointerCancel(event) {
    if (releasePointer(event)) {
      return true;
    }
    if (
      compatibilityMarker === null ||
      (event?.pointerId !== undefined &&
        event.pointerId !== compatibilityMarker.pointerId)
    ) {
      return false;
    }
    const flatSlot = compatibilityMarker.flatSlot;
    compatibilityMarker = null;
    if (pressed.delete(flatSlot)) {
      publishPressed();
    }
    return true;
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
      mouseSlot = null;
      const count = pressed.size;
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
  editable = isEditableTarget,
  onPressedChange = () => {},
}) {
  requireTrigger(trigger);
  requireVelocity(velocity);
  if (typeof editable !== "function") {
    throw new TypeError("Keyboard editable detection must be a function");
  }
  if (typeof onPressedChange !== "function") {
    throw new TypeError("Keyboard pressed-state notification must be a function");
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
    onPressedChange(pressed.size);
    trigger(codeToSlot.get(code), velocity);
    return true;
  }

  function keyUp(event) {
    const changed = pressed.delete(event?.code);
    if (changed) {
      onPressedChange(pressed.size);
    }
    return changed;
  }

  function clearPressed() {
    const count = pressed.size;
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
  onPressedChange = () => {},
}) {
  requireTrigger(trigger);
  if (
    typeof requestMIDIAccess !== "function" ||
    typeof notify !== "function" ||
    typeof onPressedChange !== "function"
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

  function publishPressed() {
    onPressedChange(diagnostics().pressed_note_count);
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
    if (permission !== "granted" || !connectedInputs.has(input)) {
      return false;
    }
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
    pressed.add(note);
    publishPressed();
    trigger(slotStart + offset, velocity);
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
    const lostPressedNotes = pressedByInput.get(input)?.size ?? 0;
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
        notes.clear();
      }
      publishPressed();
      return count;
    },
    dispose,
  });
}
