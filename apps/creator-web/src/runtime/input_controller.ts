import {
  DEFAULT_KEYBOARD_MAPPING,
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
} from "@lmdj/web-runtime-platform/input_adapters.mjs";
import type {PerformanceRawEvent} from
  "@lmdj/web-runtime-platform/runtime_types";

import type {CreatorAction, Bank} from "../state/creator_state";
import type {
  CreatorSampleRuntimeSession,
  CreatorRuntimeSession,
  PadPlayback,
  RuntimeOutcome,
  RuntimeTriggerSource,
  RuntimeVoiceState,
  SampleTriggerMode,
  TriggerAdmission,
  TypedRuntimeError,
} from "./runtime_types";
import {inspectSampleJourney} from "./sample_actions";
import {projectSamplePlayback} from "../state/sample_state";

const SAMPLE_TRIGGER_MODES = new Set<SampleTriggerMode>([
  "one_shot",
  "gate",
  "loop_gate",
  "loop_toggle",
]);
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

export type PerformancePadInputEvent = Extract<
  PerformanceRawEvent,
  Readonly<{kind: "pad_press" | "pad_release"}>
>;

interface CreatorInputControllerCommonOptions {
  getActiveBank: () => Bank;
  dispatch: (action: CreatorAction) => void;
  requestMIDIAccess?: (options: {sysex: false}) => Promise<MidiAccessLike>;
  now?: () => number;
  windowTarget?: Window;
  documentTarget?: Document;
  getArmedCaptureSlot?: () => number | null;
  onArmedCaptureStop?: (slot: number, source: RuntimeTriggerSource) => void;
  createPerformanceGestureId?: () => string;
  onPerformancePadEvent?: (
    event: PerformancePadInputEvent,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) => void;
}

interface CreatorLegacyInputControllerOptions
  extends CreatorInputControllerCommonOptions {
  session: CreatorRuntimeSession;
  isAssigned: (slot: number) => boolean;
  isAvailable?: never;
  onFilePickIntent?: never;
}

interface CreatorSampleInputControllerOptions
  extends CreatorInputControllerCommonOptions {
  session: CreatorSampleRuntimeSession;
  isAssigned: (slot: number) => boolean;
  isAvailable: (slot: number) => boolean;
  isRuntimeCurrent: () => boolean;
  getAuditionPlayback: (slot: number) => PadPlayback | null;
  onFilePickIntent: (slot: number, source: RuntimeTriggerSource) => void;
}

type CreatorInputControllerOptions =
  | CreatorLegacyInputControllerOptions
  | CreatorSampleInputControllerOptions;

interface AdmissionRecord {
  slot: number;
  gesture: string;
  sampleToken?: SampleGestureToken;
  mode?: SampleTriggerMode | null;
  muted?: boolean;
}

interface SampleGestureToken {
  released: boolean;
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

export function createCreatorInputController(options: CreatorInputControllerOptions) {
  const {
    session,
    getActiveBank,
    dispatch,
    requestMIDIAccess,
    now = () => performance.now(),
    windowTarget = window,
    documentTarget = document,
    getArmedCaptureSlot = () => null,
    onArmedCaptureStop,
    createPerformanceGestureId = () => crypto.randomUUID(),
    onPerformancePadEvent,
  } = options;
  const sampleOptions = typeof options.onFilePickIntent === "function"
    ? options as CreatorSampleInputControllerOptions
    : null;
  const adapterAvailable = (slot: number) => getArmedCaptureSlot() === slot ||
    (sampleOptions === null
      ? (options as CreatorLegacyInputControllerOptions).isAssigned(slot)
      : true);
  const activeGestures = new Set<string>();
  const gestureModes = new Map<string, SampleTriggerMode>();
  const sampleGestureTokens = new Map<string, SampleGestureToken[]>();
  const runtimeAgnosticGestures = new Set<string>();
  const loopToggleSlots = new Map<number, number>();
  const stoppingLoopSlots = new Set<number>();
  const admissions = new Map<number, AdmissionRecord>();
  const earlyOutcomes = new Map<number, RuntimeOutcome>();
  const performanceGestureIds = new Map<object, string>();
  let sampleTriggerTail: Promise<void> | null = null;
  let disposed = false;

  const gesture = (source: RuntimeTriggerSource, slot: number) => `${source}:${slot}`;

  function observePerformancePress(
    gestureKey: object,
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
  ) {
    if (onPerformancePadEvent === undefined) return;
    try {
      const gestureId = createPerformanceGestureId();
      performanceGestureIds.set(gestureKey, gestureId);
      onPerformancePadEvent(Object.freeze({
        kind: "pad_press",
        gestureId,
        slot,
        velocity,
      }), source, gestureKey);
    } catch {
      // An optional UI observer cannot alter the established input path.
    }
  }

  function observePerformanceRelease(
    gestureKey: object,
    slot: number,
    source: RuntimeTriggerSource,
  ) {
    const gestureId = performanceGestureIds.get(gestureKey);
    if (gestureId === undefined || onPerformancePadEvent === undefined) return;
    performanceGestureIds.delete(gestureKey);
    try {
      onPerformancePadEvent(Object.freeze({
        kind: "pad_release",
        gestureId,
        slot,
      }), source, gestureKey);
    } catch {
      // An optional UI observer cannot alter release or lifecycle cleanup.
    }
  }

  function currentSampleToken(currentGesture: string) {
    return sampleGestureTokens.get(currentGesture)?.at(-1);
  }

  function addSampleToken(currentGesture: string, token: SampleGestureToken) {
    const tokens = sampleGestureTokens.get(currentGesture);
    if (tokens === undefined) {
      sampleGestureTokens.set(currentGesture, [token]);
      return;
    }
    tokens.push(token);
  }

  function hasSampleToken(currentGesture: string, token: SampleGestureToken) {
    return sampleGestureTokens.get(currentGesture)?.includes(token) === true;
  }

  function removeSampleToken(currentGesture: string, token: SampleGestureToken) {
    const tokens = sampleGestureTokens.get(currentGesture);
    if (tokens === undefined) return;
    const next = tokens.filter((candidate) => candidate !== token);
    if (next.length === 0) sampleGestureTokens.delete(currentGesture);
    else sampleGestureTokens.set(currentGesture, next);
  }

  function clearSampleAttempt(
    currentGesture: string,
    token: SampleGestureToken,
  ) {
    const ownsGesture = currentSampleToken(currentGesture) === token;
    removeSampleToken(currentGesture, token);
    if (ownsGesture) {
      activeGestures.delete(currentGesture);
      gestureModes.delete(currentGesture);
      runtimeAgnosticGestures.delete(currentGesture);
    }
    return ownsGesture;
  }

  function clearSlotGestures(slot: number) {
    for (const source of ["pointer", "keyboard", "midi"] as const) {
      const current = gesture(source, slot);
      activeGestures.delete(current);
      gestureModes.delete(current);
      sampleGestureTokens.delete(current);
      runtimeAgnosticGestures.delete(current);
    }
  }

  function slotHasActiveGesture(slot: number) {
    return (["pointer", "keyboard", "midi"] as const).some((source) =>
      activeGestures.has(gesture(source, slot))
    );
  }

  function hasAcceptedLoopToggle(slot: number) {
    if (loopToggleSlots.has(slot)) return true;
    return Array.from(admissions.values()).some((admission) =>
      admission.slot === slot && admission.mode === "loop_toggle" &&
      admission.muted !== true
    );
  }

  function discardLoopToggleAdmissions(slot: number) {
    for (const [sequence, admission] of admissions) {
      if (admission.slot === slot && admission.mode === "loop_toggle") {
        admissions.delete(sequence);
      }
    }
  }

  function stopAcceptedLoopToggle(slot: number) {
    if (!hasAcceptedLoopToggle(slot)) return false;
    if (stoppingLoopSlots.has(slot)) return true;
    if (sampleOptions === null) return false;
    stoppingLoopSlots.add(slot);
    sampleControl(sampleOptions.session.stopPad(slot), {
      accepted() {
        stoppingLoopSlots.delete(slot);
        loopToggleSlots.delete(slot);
        discardLoopToggleAdmissions(slot);
        clearSlotGestures(slot);
        dispatch({type: "pad-released", slot});
      },
      rejected() {
        stoppingLoopSlots.delete(slot);
      },
    });
    return true;
  }

  function sampleControl(
    result: Promise<boolean>,
    callbacks: {
      accepted?: () => void;
      rejected?: () => void;
    } = {},
  ) {
    void result.then(
      (accepted) => {
        if (disposed) return;
        if (typeof accepted !== "boolean") {
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_PROTOCOL_MISMATCH",
          });
          callbacks.rejected?.();
        } else if (!accepted) {
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_STATE_INVALID",
          });
          callbacks.rejected?.();
        } else {
          callbacks.accepted?.();
        }
      },
      (error: unknown) => {
        if (!disposed) {
          dispatch(inputErrorAction(error));
          callbacks.rejected?.();
        }
      },
    );
  }

  function release(
    slot: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    const currentGesture = gesture(source, slot);
    observePerformanceRelease(gestureKey, slot, source);
    const mode = gestureModes.get(currentGesture);
    const sampleToken = currentSampleToken(currentGesture);
    if (sampleOptions !== null) {
      if (runtimeAgnosticGestures.has(currentGesture)) {
        const wasActive = activeGestures.delete(currentGesture);
        runtimeAgnosticGestures.delete(currentGesture);
        if (sampleToken !== undefined) {
          removeSampleToken(currentGesture, sampleToken);
        }
        dispatch({type: "pad-released", slot});
        if (wasActive) {
          sampleControl(sampleOptions.session.release(slot, source));
        }
        return;
      }
      if (mode === "loop_toggle" && loopToggleSlots.has(slot)) return;
      if (sampleToken !== undefined &&
        (mode === undefined || mode === "loop_toggle")) {
        sampleToken.released = true;
        activeGestures.delete(currentGesture);
        dispatch({type: "pad-released", slot});
        return;
      }
    }
    const wasActive = activeGestures.delete(currentGesture);
    gestureModes.delete(currentGesture);
    if (sampleToken !== undefined) {
      removeSampleToken(currentGesture, sampleToken);
    }
    dispatch({type: "pad-released", slot});
    if (sampleOptions !== null && wasActive &&
      (mode === "gate" || mode === "loop_gate")) {
      sampleControl(sampleOptions.session.release(slot, source));
    }
  }

  function cancelGesture(
    slot: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    const currentGesture = gesture(source, slot);
    observePerformanceRelease(gestureKey, slot, source);
    const mode = gestureModes.get(currentGesture);
    const shouldRelease = activeGestures.has(currentGesture) &&
      (runtimeAgnosticGestures.has(currentGesture) ||
        mode === "gate" || mode === "loop_gate");
    activeGestures.delete(currentGesture);
    gestureModes.delete(currentGesture);
    const sampleToken = currentSampleToken(currentGesture);
    if (sampleToken !== undefined) {
      removeSampleToken(currentGesture, sampleToken);
    }
    runtimeAgnosticGestures.delete(currentGesture);
    dispatch({type: "pad-released", slot});
    if (sampleOptions !== null && shouldRelease) {
      sampleControl(sampleOptions.session.release(slot, source));
    }
  }

  function applyOutcome(outcome: RuntimeOutcome, admission: AdmissionRecord) {
    const tokenCurrent = admission.sampleToken === undefined ||
      hasSampleToken(admission.gesture, admission.sampleToken);
    if (!tokenCurrent) {
      return;
    }
    if (outcome.outcome === "voice_capacity") {
      admissions.delete(outcome.sequence);
      if (admission.mode === "loop_toggle") {
        loopToggleSlots.delete(admission.slot);
        stoppingLoopSlots.delete(admission.slot);
      }
      dispatch({type: "pad-pressed", slot: admission.slot, outcome: "capacity"});
      if (admission.sampleToken?.released === true ||
          !activeGestures.has(admission.gesture)) {
        const clearedGesture = admission.sampleToken === undefined
          ? activeGestures.delete(admission.gesture)
          : clearSampleAttempt(admission.gesture, admission.sampleToken);
        if (admission.sampleToken === undefined) {
          gestureModes.delete(admission.gesture);
          runtimeAgnosticGestures.delete(admission.gesture);
        }
        if (clearedGesture) {
          dispatch({type: "pad-released", slot: admission.slot});
        }
      }
      return;
    }
    if (admission.mode === "loop_toggle" && !admission.muted) {
      loopToggleSlots.set(admission.slot, outcome.sequence);
      dispatch({type: "pad-pressed", slot: admission.slot, outcome: "started"});
      return;
    }
    if (!activeGestures.has(admission.gesture)) {
      if (admission.sampleToken !== undefined) {
        removeSampleToken(admission.gesture, admission.sampleToken);
      }
      gestureModes.delete(admission.gesture);
      return;
    }
    dispatch({
      type: "pad-pressed",
      slot: admission.slot,
      outcome: "started",
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

  function observeVoiceState(event: RuntimeVoiceState) {
    if (disposed || !Number.isSafeInteger(event.sequence) || event.sequence <= 0 ||
      !Number.isSafeInteger(event.slot) || event.slot < 0 || event.slot > 63 ||
      !["started", "stopped", "completed"].includes(event.state) ||
      !Number.isSafeInteger(event.runtimeFrame) || event.runtimeFrame < 0 ||
      !Number.isSafeInteger(event.sourceFrame) || event.sourceFrame < 0 ||
      Object.keys(event).length !== 5) {
      return;
    }
    dispatch({
      type: "sample-action",
      action: {type: "voice-changed", event},
    });
    const admission = admissions.get(event.sequence);
    const admissionCurrent = admission?.sampleToken === undefined ||
      hasSampleToken(admission.gesture, admission.sampleToken);
    if (event.state === "started" && admission?.mode === "loop_toggle" &&
        !admission.muted && admissionCurrent) {
      loopToggleSlots.set(event.slot, event.sequence);
      dispatch({type: "pad-pressed", slot: event.slot, outcome: "started"});
      return;
    }
    if (event.state === "stopped" || event.state === "completed") {
      const matchedLatch = loopToggleSlots.get(event.slot) === event.sequence;
      if (matchedLatch) {
        loopToggleSlots.delete(event.slot);
        stoppingLoopSlots.delete(event.slot);
      }
      let clearedGesture = false;
      if (admission !== undefined && admissionCurrent) {
        if (admission.sampleToken === undefined) {
          activeGestures.delete(admission.gesture);
          gestureModes.delete(admission.gesture);
          runtimeAgnosticGestures.delete(admission.gesture);
          clearedGesture = true;
        } else {
          clearedGesture = clearSampleAttempt(
            admission.gesture,
            admission.sampleToken,
          );
        }
      }
      admissions.delete(event.sequence);
      if ((matchedLatch || clearedGesture) && !slotHasActiveGesture(event.slot)) {
        dispatch({type: "pad-released", slot: event.slot});
      }
    }
  }

  function sessionTrigger(
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
    currentGesture: string,
    mode: SampleTriggerMode | null,
    sampleToken?: SampleGestureToken,
    muted = false,
  ) {
    const clearRejectedAttempt = () => {
      if (sampleToken === undefined) {
        activeGestures.delete(currentGesture);
        gestureModes.delete(currentGesture);
        runtimeAgnosticGestures.delete(currentGesture);
        return true;
      }
      return clearSampleAttempt(currentGesture, sampleToken);
    };
    return session.trigger(slot, velocity, source).then(
      (admission) => {
        if (disposed) return;
        const currentSampleAttempt = sampleToken === undefined ||
          hasSampleToken(currentGesture, sampleToken);
        if (admission === false) {
          if (currentSampleAttempt) {
            const clearedGesture = clearRejectedAttempt();
            if (mode === "loop_toggle") loopToggleSlots.delete(slot);
            if (clearedGesture) dispatch({type: "pad-released", slot});
          }
          return;
        }
        if (!admissionMatches(admission, slot, velocity, source)) {
          if (currentSampleAttempt) {
            const clearedGesture = clearRejectedAttempt();
            if (mode === "loop_toggle") loopToggleSlots.delete(slot);
            if (clearedGesture) dispatch({type: "pad-released", slot});
          }
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_PROTOCOL_MISMATCH",
          });
          return;
        }
        if (!currentSampleAttempt) return;
        const record: AdmissionRecord = sampleToken === undefined
          ? {slot, gesture: currentGesture, mode, muted}
          : {slot, gesture: currentGesture, sampleToken, mode, muted};
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
        if (!disposed) {
          const currentSampleAttempt = sampleToken === undefined ||
            hasSampleToken(currentGesture, sampleToken);
          if (currentSampleAttempt) {
            const clearedGesture = clearRejectedAttempt();
            if (mode === "loop_toggle") loopToggleSlots.delete(slot);
            if (clearedGesture) dispatch({type: "pad-released", slot});
          }
          dispatch(inputErrorAction(error));
        }
      },
    );
  }

  function trigger(
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    const currentGesture = gesture(source, slot);
    observePerformancePress(gestureKey, slot, velocity, source);
    const armedCaptureSlot = getArmedCaptureSlot();
    if (armedCaptureSlot === slot && onArmedCaptureStop !== undefined) {
      onArmedCaptureStop(slot, source);
      return;
    }
    if (sampleOptions === null) {
      activeGestures.add(currentGesture);
      sessionTrigger(slot, velocity, source, currentGesture, null);
      return;
    }

    // The capture owns Sample selection until it commits or is discarded.
    // Other Pads remain ordinary playable Sequence input, but must not retarget
    // the pending Sample mutation away from the armed capture identity.
    if (armedCaptureSlot === null) {
      dispatch({
        type: "sample-action",
        action: {type: "slot-selected", slot},
      });
    }
    if (stopAcceptedLoopToggle(slot)) return;
    if (!sampleOptions.isAssigned(slot)) {
      sampleOptions.onFilePickIntent(slot, source);
      return;
    }
    if (!sampleOptions.isAvailable(slot)) return;

    const sampleToken: SampleGestureToken = {released: false};
    activeGestures.add(currentGesture);
    addSampleToken(currentGesture, sampleToken);
    if (!sampleOptions.isRuntimeCurrent()) {
      runtimeAgnosticGestures.add(currentGesture);
      sessionTrigger(
        slot,
        velocity,
        source,
        currentGesture,
        null,
        sampleToken,
      );
      return;
    }
    const action = async () => {
      if (disposed || !hasSampleToken(currentGesture, sampleToken)) {
        return;
      }
      if (stopAcceptedLoopToggle(slot)) {
        removeSampleToken(currentGesture, sampleToken);
        return;
      }
      try {
        const inspect = await inspectSampleJourney(sampleOptions.session, slot);
        if (disposed || !hasSampleToken(currentGesture, sampleToken)) {
          return;
        }
        if (inspect.assetId === null) {
          if (clearSampleAttempt(currentGesture, sampleToken)) {
            dispatch({type: "pad-released", slot});
          }
          sampleOptions.onFilePickIntent(slot, source);
          return;
        }
        if (!sampleOptions.isAvailable(slot)) {
          if (clearSampleAttempt(currentGesture, sampleToken)) {
            dispatch({type: "pad-released", slot});
          }
          return;
        }
        if (!sampleOptions.isRuntimeCurrent()) {
          runtimeAgnosticGestures.add(currentGesture);
          if (sampleToken.released) activeGestures.add(currentGesture);
          await sessionTrigger(
            slot,
            velocity,
            source,
            currentGesture,
            null,
            sampleToken,
          );
          if (sampleToken.released) release(slot, source, gestureKey);
          return;
        }
        let effectivePlayback = inspect.playback;
        try {
          const auditionPlayback = sampleOptions.getAuditionPlayback(slot);
          if (auditionPlayback !== null) {
            effectivePlayback = projectSamplePlayback(auditionPlayback);
          }
        } catch {
          if (clearSampleAttempt(currentGesture, sampleToken)) {
            dispatch({type: "pad-released", slot});
          }
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_PROTOCOL_MISMATCH",
          });
          return;
        }
        const mode = effectivePlayback.triggerMode;
        if (!SAMPLE_TRIGGER_MODES.has(mode)) {
          if (clearSampleAttempt(currentGesture, sampleToken)) {
            dispatch({type: "pad-released", slot});
          }
          dispatch({
            type: "runtime-changed",
            phase: "failed",
            errorCode: "HOST_PROTOCOL_MISMATCH",
          });
          return;
        }
        const ownsGesture = currentSampleToken(currentGesture) === sampleToken;
        if (ownsGesture) gestureModes.set(currentGesture, mode);
        if (sampleToken.released &&
          (mode === "gate" || mode === "loop_gate")) {
          clearSampleAttempt(currentGesture, sampleToken);
          return;
        }
        await sessionTrigger(
          slot,
          velocity,
          source,
          currentGesture,
          mode,
          sampleToken,
          effectivePlayback.muted,
        );
      } catch (error: unknown) {
        if (disposed || !hasSampleToken(currentGesture, sampleToken)) {
          return;
        }
        if (clearSampleAttempt(currentGesture, sampleToken)) {
          dispatch({type: "pad-released", slot});
        }
        dispatch(inputErrorAction(error));
      }
    };
    const journey = sampleTriggerTail === null
      ? action()
      : sampleTriggerTail.then(action);
    const completion = journey.then(
      () => undefined,
      () => undefined,
    );
    sampleTriggerTail = completion;
    void completion.then(() => {
      if (sampleTriggerTail === completion) sampleTriggerTail = null;
    });
  }

  const resolveSlot = (localSlot: number) => getActiveBank() * 16 + localSlot;
  const pointer = createPointerAdapter({
    trigger,
    velocity: 100,
    isAvailable: adapterAvailable,
    now,
    onRelease: release,
    onCancel: cancelGesture,
  });
  const keyboard = createKeyboardAdapter({
    trigger,
    mapping: DEFAULT_KEYBOARD_MAPPING,
    velocity: 100,
    resolveSlot,
    isAvailable: adapterAvailable,
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
    isAvailable: adapterAvailable,
    onRelease: release,
  });
  const unsubscribeOutcome = session.subscribeRuntimeOutcome(observeOutcome);
  const unsubscribeVoice = sampleOptions === null
    ? () => {}
    : sampleOptions.session.subscribeVoiceState(observeVoiceState);
  const onBlur = () => clearAdversePressed();
  const onKeyDown = (event: KeyboardEvent) => { keyboard.keyDown(event); };
  const onKeyUp = (event: KeyboardEvent) => { keyboard.keyUp(event); };
  const onPointerUp = (event: PointerEvent) => { pointer.releasePointer(event); };
  const onPointerCancel = (event: PointerEvent) => { pointer.pointerCancel(event); };
  const onMouseUp = (event: MouseEvent) => { pointer.releaseMouse(event); };
  const onPageHide = (event: PageTransitionEvent) => {
    if (event.persisted) {
      clearAdversePressed();
      return;
    }
    dispose();
  };
  const onVisibility = () => {
    if (documentTarget.visibilityState === "hidden") clearAdversePressed();
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
    gestureModes.clear();
    for (const [currentGesture, tokens] of sampleGestureTokens) {
      const released = tokens.filter((token) => token.released);
      if (released.length === 0) sampleGestureTokens.delete(currentGesture);
      else sampleGestureTokens.set(currentGesture, released);
    }
    runtimeAgnosticGestures.clear();
    if (sampleOptions === null) {
      admissions.clear();
      earlyOutcomes.clear();
    }
    dispatch({type: "pressed-cleared"});
  }

  function clearAdversePressed() {
    activeGestures.clear();
    gestureModes.clear();
    sampleGestureTokens.clear();
    runtimeAgnosticGestures.clear();
    loopToggleSlots.clear();
    stoppingLoopSlots.clear();
    admissions.clear();
    earlyOutcomes.clear();
    pointer.clearPressed();
    keyboard.clearPressed();
    midi.clearPressed();
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
    unsubscribeVoice();
    clearAdversePressed();
    midi.dispose();
    performanceGestureIds.clear();
    gestureModes.clear();
    sampleGestureTokens.clear();
    runtimeAgnosticGestures.clear();
    loopToggleSlots.clear();
    stoppingLoopSlots.clear();
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
      return slot === undefined ? released : released || pointer.pointerUp(event, slot);
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
