import {
  DEFAULT_KEYBOARD_MAPPING,
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
} from "@lmdj/web-runtime-platform/input_adapters.mjs";

import type {CreatorAction, Bank} from "../state/creator_state";
import type {
  CreatorRuntimeSession,
  RuntimeOutcome,
  RuntimeTriggerSource,
  TriggerAdmission,
  TypedRuntimeError,
} from "./runtime_types";

interface PointerInput {
  type?: string;
  isPrimary?: boolean;
  button?: number;
  pointerId?: number;
  clientX?: number;
  clientY?: number;
  target?: EventTarget | null;
}

interface KeyboardInput {
  code?: string;
  repeat?: boolean;
  target?: EventTarget | null;
}

interface MidiAccessLike {
  inputs?: {values(): Iterable<unknown>};
  addEventListener?(type: string, listener: (event: unknown) => void): void;
  removeEventListener?(type: string, listener: (event: unknown) => void): void;
}

interface CreatorInputControllerOptions {
  session: CreatorRuntimeSession;
  getActiveBank: () => Bank;
  isAssigned: (slot: number) => boolean;
  dispatch: (action: CreatorAction) => void;
  requestMIDIAccess?: (options: {sysex: false}) => Promise<MidiAccessLike>;
  now?: () => number;
  windowTarget?: Window;
  documentTarget?: Document;
}

interface AdmissionRecord {
  slot: number;
  gesture: string;
}

function inputErrorAction(error: unknown): CreatorAction {
  const code = (error as TypedRuntimeError | null)?.code ?? "INTERNAL_ERROR";
  return {
    type: "runtime-changed",
    phase: code === "HOST_RESTART_REQUIRED" || code === "HOST_TIMEOUT"
      ? "restart-required"
      : "failed",
    errorCode: code,
  };
}

function admissionMatches(
  value: TriggerAdmission,
  slot: number,
  velocity: number,
  source: RuntimeTriggerSource,
): boolean {
  return Number.isSafeInteger(value.sequence) && value.sequence > 0 &&
    value.slot === slot && value.velocity === velocity && value.source === source;
}

export function createCreatorInputController({
  session,
  getActiveBank,
  isAssigned,
  dispatch,
  requestMIDIAccess,
  now = () => performance.now(),
  windowTarget = window,
  documentTarget = document,
}: CreatorInputControllerOptions) {
  const activeGestures = new Set<string>();
  const admissions = new Map<number, AdmissionRecord>();
  const earlyOutcomes = new Map<number, RuntimeOutcome>();
  let disposed = false;

  const gesture = (source: RuntimeTriggerSource, slot: number) => `${source}:${slot}`;

  function release(slot: number, source: RuntimeTriggerSource) {
    activeGestures.delete(gesture(source, slot));
    dispatch({type: "pad-released", slot});
  }

  function applyOutcome(outcome: RuntimeOutcome, admission: AdmissionRecord) {
    if (!activeGestures.has(admission.gesture)) return;
    dispatch({
      type: "pad-pressed",
      slot: admission.slot,
      outcome: outcome.outcome === "voice_started" ? "started" : "capacity",
    });
  }

  function observeOutcome(outcome: RuntimeOutcome) {
    if (disposed) return;
    const admission = admissions.get(outcome.sequence);
    if (!admission) {
      if (earlyOutcomes.size < 4_096) earlyOutcomes.set(outcome.sequence, outcome);
      return;
    }
    applyOutcome(outcome, admission);
  }

  function trigger(slot: number, velocity: number, source: RuntimeTriggerSource) {
    const currentGesture = gesture(source, slot);
    activeGestures.add(currentGesture);
    void session.trigger(slot, velocity, source).then(
      (admission) => {
        if (disposed || admission === false) return;
        if (!admissionMatches(admission, slot, velocity, source)) {
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_PROTOCOL_MISMATCH",
          });
          return;
        }
        const record = {slot, gesture: currentGesture};
        if (admissions.size >= 4_096) {
          admissions.delete(admissions.keys().next().value as number);
        }
        admissions.set(admission.sequence, record);
        if (activeGestures.has(currentGesture)) {
          dispatch({type: "pad-pressed", slot, outcome: "admitted"});
        }
        const early = earlyOutcomes.get(admission.sequence);
        if (early) {
          earlyOutcomes.delete(admission.sequence);
          applyOutcome(early, record);
        }
      },
      (error: unknown) => {
        if (!disposed) dispatch(inputErrorAction(error));
      },
    );
  }

  const resolveSlot = (localSlot: number) => getActiveBank() * 16 + localSlot;
  const pointer = createPointerAdapter({
    trigger,
    velocity: 100,
    isAvailable: isAssigned,
    now,
    onRelease: release,
  });
  const keyboard = createKeyboardAdapter({
    trigger,
    mapping: DEFAULT_KEYBOARD_MAPPING,
    velocity: 100,
    resolveSlot,
    isAvailable: isAssigned,
    onRelease: release,
  });
  const midiRequest = requestMIDIAccess ?? ((options: {sysex: false}) => {
    const navigatorWithMidi = windowTarget.navigator as Navigator & {
      requestMIDIAccess?: (value: {sysex: false}) => Promise<MidiAccessLike>;
    };
    if (typeof navigatorWithMidi.requestMIDIAccess !== "function") {
      return Promise.reject(new Error("Web MIDI is unavailable"));
    }
    return navigatorWithMidi.requestMIDIAccess(options);
  });
  const midi = createMidiAdapter({
    trigger,
    requestMIDIAccess: midiRequest,
    notify: () => {},
    noteStart: 36,
    slotStart: 0,
    slotCount: 16,
    resolveSlot,
    isAvailable: isAssigned,
    onRelease: release,
  });
  const unsubscribeOutcome = session.subscribeRuntimeOutcome(observeOutcome);
  const onBlur = () => clearPressed();
  const onKeyDown = (event: KeyboardEvent) => { keyboard.keyDown(event); };
  const onKeyUp = (event: KeyboardEvent) => { keyboard.keyUp(event); };
  const onPointerUp = (event: PointerEvent) => { pointer.releasePointer(event); };
  const onPointerCancel = (event: PointerEvent) => { pointer.pointerCancel(event); };
  const onMouseUp = (event: MouseEvent) => { pointer.releaseMouse(event); };
  const onPageHide = (event: PageTransitionEvent) => {
    if (event.persisted) {
      clearPressed();
      return;
    }
    dispose();
  };
  const onVisibility = () => {
    if (documentTarget.visibilityState === "hidden") clearPressed();
  };
  windowTarget.addEventListener("blur", onBlur);
  windowTarget.addEventListener("keydown", onKeyDown);
  windowTarget.addEventListener("keyup", onKeyUp);
  windowTarget.addEventListener("pointerup", onPointerUp);
  windowTarget.addEventListener("pointercancel", onPointerCancel);
  windowTarget.addEventListener("mouseup", onMouseUp);
  windowTarget.addEventListener("pagehide", onPageHide);
  documentTarget.addEventListener("visibilitychange", onVisibility);

  function clearPressed() {
    pointer.clearPressed();
    keyboard.clearPressed();
    midi.clearPressed();
    activeGestures.clear();
    dispatch({type: "pressed-cleared"});
  }

  function dispose() {
    if (disposed) return;
    disposed = true;
    windowTarget.removeEventListener("blur", onBlur);
    windowTarget.removeEventListener("keydown", onKeyDown);
    windowTarget.removeEventListener("keyup", onKeyUp);
    windowTarget.removeEventListener("pointerup", onPointerUp);
    windowTarget.removeEventListener("pointercancel", onPointerCancel);
    windowTarget.removeEventListener("mouseup", onMouseUp);
    windowTarget.removeEventListener("pagehide", onPageHide);
    documentTarget.removeEventListener("visibilitychange", onVisibility);
    unsubscribeOutcome();
    clearPressed();
    midi.dispose();
    admissions.clear();
    earlyOutcomes.clear();
  }

  return Object.freeze({
    pointerDown(event: PointerInput, slot: number) {
      return event.type === "mousedown"
        ? pointer.mouseDown(event, slot)
        : pointer.pointerDown(event, slot);
    },
    pointerUp(event: PointerInput, slot: number) {
      if (event.type === "mouseup") {
        return pointer.releaseMouse(event) || pointer.pointerUp(event, slot);
      }
      return pointer.releasePointer(event) || pointer.pointerUp(event, slot);
    },
    pointerCancel(event: PointerInput, slot?: number) {
      const released = pointer.pointerCancel(event);
      return slot === undefined ? released : pointer.pointerUp(event, slot) || released;
    },
    keyDown(event: KeyboardInput) {
      return keyboard.keyDown(event);
    },
    keyUp(event: KeyboardInput) {
      return keyboard.keyUp(event);
    },
    async enableMidi() {
      try {
        await midi.requestPermission();
        return true;
      } catch {
        return false;
      }
    },
    clearPressed,
    dispose,
  });
}
