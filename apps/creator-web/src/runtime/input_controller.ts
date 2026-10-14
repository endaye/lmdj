import {
  DEFAULT_KEYBOARD_MAPPING,
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
} from "@lmdj/web-runtime-platform/input_adapters.mjs";
import type {InputGestureLease, PerformanceRawEvent} from
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
  isTrusted?: boolean;
  nativeEvent?: {isTrusted: boolean; type?: string; pointerType?: string};
  type?: string;
  pointerType?: string;
  isPrimary?: boolean;
  button?: number;
  pointerId?: number;
  clientX?: number;
  clientY?: number;
  target?: EventTarget | null;
}

interface KeyboardInput {
  isTrusted?: boolean;
  nativeEvent?: {isTrusted: boolean};
  code?: string;
  type?: string;
  repeat?: boolean;
  ctrlKey?: boolean;
  metaKey?: boolean;
  altKey?: boolean;
  shiftKey?: boolean;
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
  onInputObservationError?: (error: unknown) => void;
  onAdverseLifecycle?: () => void;
  canUsePad?: (slot: number) => boolean;
  onEmptyPadPress?: (slot: number, key: object, source: RuntimeTriggerSource,
    activation: Promise<boolean> | null) => boolean;
  onEmptyPadRelease?: (key: object) => void;
  onEmptyPadCancel?: (key?: object) => void;
  activateAudioForGesture?: (event: {isTrusted: boolean}) => Promise<boolean> | null;
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

interface PhysicalGesture {
  slot: number;
  source: RuntimeTriggerSource;
  released: boolean;
  triggerInvoked: boolean;
  releaseSubmitted: boolean;
}

interface SampleGestureToken {
  released: boolean;
  gestureKey: object;
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
  return value !== null && typeof value === "object" &&
    Number.isSafeInteger(value.sequence) && value.sequence > 0 &&
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
  const captureGestures = new Set<object>();
  const gestureModes = new Map<string, SampleTriggerMode>();
  const sampleGestureTokens = new Map<string, SampleGestureToken[]>();
  // A voice or visual token can end while its physical input is still held.
  const physicalGestures = new Map<object, PhysicalGesture>();
  const inputLeases = new Map<object, InputGestureLease>();
  function cancelPatternPreparation(key: object) {
    inputLeases.get(key)?.cancelUnsubmittedPattern();
    if (physicalGestures.get(key)?.released) inputLeases.delete(key);
  }
  function endPhysicalInput(key: object) {
    inputLeases.get(key)?.releasePhysical();
    const physical = physicalGestures.get(key);
    if (physical === undefined || physical.triggerInvoked) inputLeases.delete(key);
    // Do not cancel preparation here: a released queued one-shot may still
    // legally play. Its own cancellation/transfer settles that interest.
  }
  const runtimeAgnosticGestures = new Set<string>();
  const loopToggleSlots = new Map<number, number>();
  const stoppingLoopSlots = new Set<number>();
  const pendingLoopAdmissions = new Map<number, Promise<void>>();
  const admissions = new Map<number, AdmissionRecord>();
  const earlyOutcomes = new Map<number, RuntimeOutcome>();
  const performanceGestureIds = new Map<object, string>();
  let sampleTriggerTail: Promise<void> | null = null;
  let disposed = false;
  let inputEvent: {isTrusted: boolean; type?: string; pointerType?: string} | null = null;
  let inputGeneration = 0;
  const pendingTouchWakes = new Map<object, (ready: boolean) => void>();

  function withInputEvent<T>(event: PointerInput | KeyboardInput, action: () => T): T {
    const previous = inputEvent;
    inputEvent = event.nativeEvent ?? {isTrusted: event.isTrusted === true,
      ...(event.type === undefined ? {} : {type: event.type}),
      ...("pointerType" in event && event.pointerType !== undefined
        ? {pointerType: event.pointerType} : {})};
    try { return action(); } finally { inputEvent = previous; }
  }

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
    const physical = physicalGestures.get(token.gestureKey);
    if (physical !== undefined && !physical.triggerInvoked) {
      cancelPatternPreparation(token.gestureKey);
      physicalGestures.delete(token.gestureKey);
    }
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

  function reportInputObservationError(error: unknown, operation: "press" | "release") {
    const issue = error as TypedRuntimeError | null;
    if (issue?.code === "HOST_TIMEOUT" &&
        (issue.details?.pending === true ||
          (operation === "press" && issue.details?.pending === false))) {
      const diagnostics = session.diagnostics();
      if (diagnostics.state === "running" && diagnostics.error_code === null) {
        // A retained observation or a definitely unsubmitted Press expired.
        // Neither is a Runtime failure. Pending owner debts stay in the SDK;
        // a matching Release's definite failure keeps its original handling.
        options.onInputObservationError?.(error);
        return;
      }
    }
    dispatch(inputErrorAction(error));
  }

  function submitPhysicalRelease(gestureKey: object, physical: PhysicalGesture) {
    if (typeof session.release !== "function" || !physical.triggerInvoked ||
        !physical.released || physical.releaseSubmitted) return;
    // Reserve locally before invoking the SDK. The SDK owns any unknown Native
    // debt and joins this intent with safety cleanup; UI disposal is no ACK.
    physical.releaseSubmitted = true;
    let result: Promise<boolean>;
    try {
      result = session.release(physical.slot, physical.source, gestureKey);
    } catch (error: unknown) {
      if (!disposed) dispatch(inputErrorAction(error));
      physicalGestures.delete(gestureKey);
      return;
    }
    void Promise.resolve(result).then(accepted => {
      // false is a known no-owner/refusal, not physical consume success.
      if (!disposed && typeof accepted !== "boolean") {
        dispatch({type: "runtime-changed", phase: "failed",
          errorCode: "HOST_PROTOCOL_MISMATCH"});
      }
    }, (error: unknown) => {
      if (!disposed) reportInputObservationError(error, "release");
    }).finally(() => {
      // Only our observation ends here. SDK owner/consumer debts remain there.
      if (physicalGestures.get(gestureKey) === physical) {
        physicalGestures.delete(gestureKey);
      }
    });
  }

  function releasePhysicalGesture(gestureKey: object) {
    const physical = physicalGestures.get(gestureKey);
    if (physical === undefined) return;
    physical.released = true;
    endPhysicalInput(gestureKey);
    submitPhysicalRelease(gestureKey, physical);
  }

  function release(
    slot: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    const wake = pendingTouchWakes.get(gestureKey);
    if (wake !== undefined) {
      pendingTouchWakes.delete(gestureKey);
      // Non-mouse pointerup grants browser activation; invoke the wake inside
      // this native event stack, before awaiting any Sample inspection.
      if (inputEvent?.type === "pointerup" && inputEvent.isTrusted) {
        try {
          const activation = options.activateAudioForGesture?.(inputEvent) ?? null;
          if (activation === null) wake(true);
          else void activation.then(wake, () => wake(false));
        } catch { wake(false); }
      } else wake(false);
    }
    endPhysicalInput(gestureKey);
    observePerformanceRelease(gestureKey, slot, source);
    releasePhysicalGesture(gestureKey);
    if (captureGestures.delete(gestureKey)) {
      inputLeases.delete(gestureKey);
      options.onEmptyPadRelease?.(gestureKey);
      dispatch({type: "pad-released", slot});
      return;
    }
    const currentGesture = gesture(source, slot);
    const mode = gestureModes.get(currentGesture);
    const sampleToken = sampleGestureTokens.get(currentGesture)?.find(token => token.gestureKey === gestureKey);
    if (sampleOptions !== null) {
      if (runtimeAgnosticGestures.has(currentGesture)) {
        activeGestures.delete(currentGesture);
        runtimeAgnosticGestures.delete(currentGesture);
        if (sampleToken !== undefined) {
          removeSampleToken(currentGesture, sampleToken);
        }
        dispatch({type: "pad-released", slot});
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
    activeGestures.delete(currentGesture);
    gestureModes.delete(currentGesture);
    if (sampleToken !== undefined) {
      removeSampleToken(currentGesture, sampleToken);
    }
    dispatch({type: "pad-released", slot});
  }

  function cancelGesture(
    slot: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    pendingTouchWakes.get(gestureKey)?.(false);
    pendingTouchWakes.delete(gestureKey);
    endPhysicalInput(gestureKey);
    observePerformanceRelease(gestureKey, slot, source);
    releasePhysicalGesture(gestureKey);
    if (captureGestures.delete(gestureKey)) {
      inputLeases.delete(gestureKey);
      options.onEmptyPadCancel?.(gestureKey);
      dispatch({type: "pad-released", slot});
      return;
    }
    const currentGesture = gesture(source, slot);
    activeGestures.delete(currentGesture);
    gestureModes.delete(currentGesture);
    const sampleToken = sampleGestureTokens.get(currentGesture)?.find(token => token.gestureKey === gestureKey);
    if (sampleToken !== undefined) {
      removeSampleToken(currentGesture, sampleToken);
    }
    runtimeAgnosticGestures.delete(currentGesture);
    dispatch({type: "pad-released", slot});
    const physical = physicalGestures.get(gestureKey);
    if (physical !== undefined && !physical.triggerInvoked) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
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
      action: {type: "voice-changed", event, observedAtMilliseconds: now()},
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
    physicalKey = sampleToken?.gestureKey,
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
    const physical = physicalKey === undefined
      ? undefined : physicalGestures.get(physicalKey);
    if (physical !== undefined) physical.triggerInvoked = true;
    let triggerResult: Promise<TriggerAdmission | false>;
    try {
      triggerResult = physicalKey === undefined
        ? session.trigger(slot, velocity, source)
        : session.trigger(slot, velocity, source, physicalKey);
      // The synchronous SDK entry has transferred or refused preparation.
      if (physicalKey !== undefined) cancelPatternPreparation(physicalKey);
    } catch (error: unknown) {
      if (physicalKey !== undefined) cancelPatternPreparation(physicalKey);
      triggerResult = Promise.reject(error);
    }
    // Keyup may precede inspection or await the original trigger's durable
    // result. Submit directly after invocation, never after its completion.
    if (physical !== undefined && physicalKey !== undefined) {
      submitPhysicalRelease(physicalKey, physical);
    }
    return triggerResult.then(
      (admission) => {
        if (disposed) return;
        const currentSampleAttempt = sampleToken === undefined ||
          hasSampleToken(currentGesture, sampleToken);
        if (admission === false) {
          // This press definitely owns no Native input. Do not erase unknown
          // errors/malformed admissions through this known-refusal path.
          if (sampleToken !== undefined && physical !== undefined &&
              !physical.releaseSubmitted) {
            physicalGestures.delete(sampleToken.gestureKey);
          }
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
          reportInputObservationError(error, "press");
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
    if (options.canUsePad?.(slot) === false) return;
    const lease = session.reserveInputGesture?.(gestureKey, slot, source);
    if (lease === null) return; // No observer, wake or queue can retain a refused Press.
    if (lease !== undefined) inputLeases.set(gestureKey, lease);
    if (sampleOptions !== null || lease !== undefined)
      physicalGestures.set(gestureKey, {slot, source, released: false,
        triggerInvoked: false, releaseSubmitted: false});
    try { triggerPrepared(slot, velocity, source, gestureKey); }
    catch (error: unknown) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
      dispatch(inputErrorAction(error));
    }
  }

  function triggerPrepared(
    slot: number,
    velocity: number,
    source: RuntimeTriggerSource,
    gestureKey: object,
  ) {
    const currentGesture = gesture(source, slot);
    // Called synchronously by the adapter, while the native musical event is
    // still active. Ignored keys and compatibility mouse events never get here.
    const deferTouchWake = inputEvent?.type === "pointerdown" &&
      inputEvent.pointerType !== undefined && inputEvent.pointerType !== "mouse" &&
      options.activateAudioForGesture !== undefined &&
      session.diagnostics().state === "audio-suspended";
    const activation = deferTouchWake
      ? new Promise<boolean>(resolve => pendingTouchWakes.set(gestureKey, resolve))
      : inputEvent === null ? null : options.activateAudioForGesture?.(inputEvent) ?? null;
    const generation = inputGeneration;
    observePerformancePress(gestureKey, slot, velocity, source);
    const armedCaptureSlot = getArmedCaptureSlot();
    if (armedCaptureSlot === slot && onArmedCaptureStop !== undefined) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
      onArmedCaptureStop(slot, source);
      return;
    }
    if (sampleOptions === null) {
      activeGestures.add(currentGesture);
      if (activation === null) {
        sessionTrigger(slot, velocity, source, currentGesture, null, undefined, false,
          typeof session.reserveInputGesture === "function" ? gestureKey : undefined);
      } else {
        void activation.then((ready) => {
          if (!disposed && generation === inputGeneration && ready) {
            return sessionTrigger(slot, velocity, source, currentGesture, null, undefined, false,
              typeof session.reserveInputGesture === "function" ? gestureKey : undefined);
          }
          cancelPatternPreparation(gestureKey);
          physicalGestures.delete(gestureKey);
        }).catch(() => {
          cancelPatternPreparation(gestureKey);
          physicalGestures.delete(gestureKey);
        }).finally(() => {
          if (generation === inputGeneration) activeGestures.delete(currentGesture);
        });
      }
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
    if (stopAcceptedLoopToggle(slot)) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
      return;
    }
    if (!sampleOptions.isAssigned(slot)) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
      if (options.onEmptyPadPress?.(slot, gestureKey, source, activation)) {
        captureGestures.add(gestureKey);
        dispatch({type: "pad-pressed", slot, outcome: "admitted"});
        return;
      }
      sampleOptions.onFilePickIntent(slot, source);
      return;
    }
    if (!sampleOptions.isAvailable(slot)) {
      cancelPatternPreparation(gestureKey);
      physicalGestures.delete(gestureKey);
      return;
    }

    const sampleToken: SampleGestureToken = {released: false, gestureKey};
    activeGestures.add(currentGesture);
    addSampleToken(currentGesture, sampleToken);
    if (activation === null && !sampleOptions.isRuntimeCurrent()) {
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
    const failSampleAttempt = (error: unknown) => {
      if (disposed || !hasSampleToken(currentGesture, sampleToken)) {
        cancelPatternPreparation(gestureKey);
        return;
      }
      if (clearSampleAttempt(currentGesture, sampleToken)) {
        dispatch({type: "pad-released", slot});
      }
      dispatch(inputErrorAction(error));
    };
    const action = async () => {
      if (disposed || generation !== inputGeneration || !hasSampleToken(currentGesture, sampleToken)) {
        cancelPatternPreparation(gestureKey);
        return;
      }
      const pendingLoop = pendingLoopAdmissions.get(slot);
      if (pendingLoop !== undefined) {
        // A same-Pad toggle needs the first admission to decide stop versus
        // start. Park outside the preparation tail so other Pads can advance.
        // Re-enter with the original token, lease and lifecycle checks.
        void pendingLoop.then(enqueue, enqueue);
        return;
      }
      if (stopAcceptedLoopToggle(slot)) {
        cancelPatternPreparation(gestureKey);
        removeSampleToken(currentGesture, sampleToken);
        physicalGestures.delete(gestureKey);
        return;
      }
      try {
        if (disposed || generation !== inputGeneration ||
            !hasSampleToken(currentGesture, sampleToken)) {
          cancelPatternPreparation(gestureKey);
          return;
        }
        const inspect = await inspectSampleJourney(sampleOptions.session, slot);
        if (disposed || generation !== inputGeneration || !hasSampleToken(currentGesture, sampleToken)) {
          cancelPatternPreparation(gestureKey);
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
          void sessionTrigger(
            slot,
            velocity,
            source,
            currentGesture,
            null,
            sampleToken,
          ).catch(failSampleAttempt);
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
        // Preparation and invocation keep their order, but the SDK's public
        // completion must not block the next already-reserved physical input.
        const completion = sessionTrigger(
          slot,
          velocity,
          source,
          currentGesture,
          mode,
          sampleToken,
          effectivePlayback.muted,
        );
        if (mode === "loop_toggle") {
          pendingLoopAdmissions.set(slot, completion);
          const clearPending = () => {
            if (pendingLoopAdmissions.get(slot) === completion) {
              pendingLoopAdmissions.delete(slot);
            }
          };
          void completion.then(clearPending, error => {
            clearPending();
            failSampleAttempt(error);
          });
        } else {
          void completion.catch(failSampleAttempt);
        }
      } catch (error: unknown) {
        failSampleAttempt(error);
      }
    };
    const enqueue = () => {
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
    };
    // A held cold touch must not occupy the Sample queue before it has a
    // legal activation. Ready gestures retain serialized Sample inspection.
    if (activation === null) enqueue();
    else void activation.then(ready => {
      if (ready) enqueue();
      else if (clearSampleAttempt(currentGesture, sampleToken)) {
        dispatch({type: "pad-released", slot});
      }
    }, error => {
      if (disposed || !hasSampleToken(currentGesture, sampleToken)) {
        cancelPatternPreparation(gestureKey);
        return;
      }
      if (clearSampleAttempt(currentGesture, sampleToken)) {
        dispatch({type: "pad-released", slot});
      }
      dispatch(inputErrorAction(error));
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
  function keyDown(event: KeyboardInput) {
    // Creator reserves Ctrl/Cmd chords for app/browser shortcuts. Filter
    // before adapter admission, activation, selection or capture side effects;
    // keyUp still releases gestures begun before a modifier was held.
    if (event.ctrlKey === true || event.metaKey === true) return false;
    return withInputEvent(event, () => keyboard.keyDown(event));
  }
  const onKeyDown = (event: KeyboardEvent) => { keyDown(event); };
  const onKeyUp = (event: KeyboardEvent) => { keyboard.keyUp(event); };
  const onPointerUp = (event: PointerEvent) => {
    withInputEvent(event, () => pointer.releasePointer(event));
  };
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
    for (const wake of pendingTouchWakes.values()) wake(false);
    pendingTouchWakes.clear();
    if (captureGestures.size > 0) options.onEmptyPadCancel?.();
    captureGestures.clear();
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
    options.onEmptyPadCancel?.();
    captureGestures.clear();
    inputGeneration += 1;
    pendingLoopAdmissions.clear();
    for (const wake of pendingTouchWakes.values()) wake(false);
    pendingTouchWakes.clear();
    options.onAdverseLifecycle?.();
    for (const [key, physical] of physicalGestures) {
      releasePhysicalGesture(key);
      if (!physical.triggerInvoked) physicalGestures.delete(key);
    }
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
    for (const [key, lease] of inputLeases) {
      lease.releasePhysical();
      lease.cancelUnsubmittedPattern();
      inputLeases.delete(key);
    }
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
      return withInputEvent(event, () => event.type === "mousedown"
        ? pointer.mouseDown(event, slot)
        : pointer.pointerDown(event, slot));
    },
    pointerUp(event: PointerInput, slot: number) {
      return withInputEvent(event, () => event.type === "mouseup"
        ? pointer.releaseMouse(event) || pointer.pointerUp(event, slot)
        : pointer.releasePointer(event) || pointer.pointerUp(event, slot));
    },
    pointerCancel(event: PointerInput, slot?: number) {
      const released = pointer.pointerCancel(event);
      return slot === undefined ? released : released || pointer.pointerUp(event, slot);
    },
    keyDown,
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
