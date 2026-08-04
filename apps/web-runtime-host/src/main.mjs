import {
  createKeyboardAdapter,
  createMidiAdapter,
  createPointerAdapter,
} from "./input_adapters.mjs";
import { PREFLIGHT_CAPABILITIES, runPreflight } from "./preflight.mjs";
import {
  HostProtocolError,
  createRequestEnvelope,
  deadlineForOperation,
  validateNotificationEnvelope,
  validateResponseEnvelope,
} from "./protocol.mjs";
import { createHostStateMachine } from "./state_machine.mjs";

const SOURCE_SHELL_MANIFEST = Object.freeze({
  product_build: "1.0.13.0",
  host_version: "1.0.0",
  protocol_version: 1,
  runtime_script: "source-shell",
});
const SOURCE_SHELL_MANIFEST_TEXT = JSON.stringify(SOURCE_SHELL_MANIFEST);
const TRIGGER_LEDGER_LIMIT = 4_096;
const RECOVERY_OUTCOME_DEADLINE_MS = 1_000;
const ALLOWED_TYPED_ERROR_CODES = new Set([
  "INVALID_ARGUMENT",
  "NOT_FOUND",
  "REVISION_CONFLICT",
  "DUPLICATE_ID",
  "UNSUPPORTED_AUDIO",
  "MISSING_ASSET",
  "INVALID_PROJECT",
  "COOK_FAILED",
  "PROVIDER_NOT_FOUND",
  "PROVIDER_FAILED",
  "PERMISSION_DENIED",
  "IO_ERROR",
  "INTERNAL_ERROR",
  "UNSUPPORTED_WEB_RUNTIME",
  "PROJECT_BUSY",
  "WEB_RUNTIME_RESOURCE_LIMIT",
  "HOST_STATE_INVALID",
  "HOST_TIMEOUT",
  "HOST_PROTOCOL_MISMATCH",
]);

function typedError(code, message = code) {
  return new HostProtocolError(code, message, {});
}

function validatedErrorCode(value, fallback = "HOST_STATE_INVALID") {
  if (ALLOWED_TYPED_ERROR_CODES.has(value)) {
    return value;
  }
  return typeof value === "string" ? "HOST_PROTOCOL_MISMATCH" : fallback;
}

function errorCode(error, fallback = "HOST_STATE_INVALID") {
  return validatedErrorCode(error?.code, fallback);
}

function requireFunction(value, name) {
  if (typeof value !== "function") {
    throw new TypeError(`${name} must be injected`);
  }
  return value;
}

function isPositiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

function generationsMatch(status) {
  return (
    isPositiveInteger(status?.control_generation) &&
    isPositiveInteger(status?.acknowledged_generation) &&
    status.control_generation === status.acknowledged_generation
  );
}

export function flattenPadSlot({ bank, pad }) {
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

function defaultCapabilities(scope) {
  const storage = scope.navigator?.storage;
  return {
    secureContext: scope.isSecureContext === true,
    crossOriginIsolated: scope.crossOriginIsolated === true,
    sharedArrayBuffer: typeof scope.SharedArrayBuffer === "function",
    webAssembly: typeof scope.WebAssembly === "object",
    audioWorklet:
      typeof scope.AudioContext === "function" &&
      "audioWorklet" in scope.AudioContext.prototype,
    opfs: typeof storage?.getDirectory === "function",
    opfsSyncAccessHandle:
      typeof scope.FileSystemFileHandle?.prototype?.createSyncAccessHandle ===
      "function",
    opfsWritableReplace:
      typeof scope.FileSystemFileHandle?.prototype?.createWritable === "function",
  };
}

async function sha256(text, crypto) {
  if (typeof crypto?.subtle?.digest !== "function") {
    throw typedError("HOST_PROTOCOL_MISMATCH", "SHA-256 is unavailable");
  }
  const digest = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(text),
  );
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function verifySourceShellManifest({ document, crypto }) {
  const expected = document
    ?.querySelector?.("meta[name='lmdj-host-manifest-sha256']")
    ?.getAttribute?.("content");
  if (typeof expected !== "string" || expected.length !== 64) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest digest is absent");
  }
  const actual = await sha256(SOURCE_SHELL_MANIFEST_TEXT, crypto);
  if (actual !== expected) {
    throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest digest does not match");
  }
  return SOURCE_SHELL_MANIFEST;
}

async function loadSourceRuntime({ window }) {
  const runtime = window?.lmdjWebRuntimeHost;
  if (
    typeof runtime?.registerAudioContext !== "function" ||
    typeof runtime?.startAudioWorklet !== "function"
  ) {
    throw typedError("HOST_STATE_INVALID", "Source runtime is not loaded");
  }
  return runtime;
}

async function defaultRuntimeTerminator({ runtime, audioContext, window }) {
  const workers = new Set([
    ...(runtime?.workers ?? []),
    ...(window?.Module?.PThread?.runningWorkers ?? []),
    ...(window?.Module?.PThread?.unusedWorkers ?? []),
  ]);
  for (const worker of workers) {
    worker?.terminate?.();
  }
  if (audioContext && audioContext.state !== "closed") {
    await audioContext.close();
  }
}

function defaultKeyboardMapping() {
  return Object.freeze({
    KeyA: 0,
    KeyS: 1,
    KeyD: 2,
    KeyF: 3,
    KeyG: 4,
    KeyH: 5,
    KeyJ: 6,
    KeyK: 7,
    KeyQ: 8,
    KeyW: 9,
    KeyE: 10,
    KeyR: 11,
    KeyT: 12,
    KeyY: 13,
    KeyU: 14,
    KeyI: 15,
  });
}

export function createWebRuntimeHostController(options = {}) {
  const document = options.document;
  const window = options.window;
  const navigator = options.navigator ?? window?.navigator;
  const crypto = options.crypto ?? window?.crypto;
  const verifyManifest =
    options.verifyManifest ?? (() => verifySourceShellManifest({ document, crypto }));
  const loadRuntime =
    options.loadRuntime ?? (() => loadSourceRuntime({ window }));
  const createAudioContext =
    options.createAudioContext ??
    ((audioOptions) => new window.AudioContext(audioOptions));
  const transport = options.transport;
  const runtimeTerminator =
    options.runtimeTerminator ??
    ((resources) => defaultRuntimeTerminator({ ...resources, window }));
  const timers = options.timers ?? {
    setTimeout: (callback, milliseconds) =>
      (typeof window?.setTimeout === "function" ? window : globalThis)
        .setTimeout(callback, milliseconds),
    clearTimeout: (handle) =>
      (typeof window?.clearTimeout === "function" ? window : globalThis)
        .clearTimeout(handle),
  };
  const monotonicNow =
    options.now ?? (() => (window?.performance ?? globalThis.performance).now());

  requireFunction(verifyManifest, "Manifest verifier");
  requireFunction(loadRuntime, "Runtime loader");
  requireFunction(createAudioContext, "AudioContext factory");
  requireFunction(runtimeTerminator, "Runtime terminator");
  requireFunction(transport?.send, "Transport send");
  requireFunction(crypto?.randomUUID, "Request UUID source");

  let manifest = SOURCE_SHELL_MANIFEST;
  let runtime = null;
  let audioContext = null;
  let contextHandle = null;
  let started = false;
  let closing = false;
  let terminalCleanupStarted = false;
  let terminalCleanupPromise = null;
  let unsubscribeTransport = null;
  let expectedContextSuspend = false;
  let visibilityHidden = false;
  let pageHidden = false;
  const activeAdverseConditions = new Set();
  let lastContextState = null;
  let recoveryEpoch = null;
  let nextRecoveryEpoch = 1;
  let activationReservation = null;
  let probeReservation = null;
  let lastErrorCode = null;
  let controlGeneration = null;
  let acknowledgedGeneration = null;
  let triggerAdmittedCount = 0;
  let triggerOutcomeCount = 0;
  let triggerRejectedCount = 0;
  const admittedSequences = new Map();
  const listenerDisposers = [];

  function element(id) {
    return document?.getElementById?.(id) ?? null;
  }

  const pads = [...(document?.querySelectorAll?.("button[data-bank][data-pad]") ?? [])];

  function renderPressed(pointerSlots = null) {
    if (pointerSlots !== null) {
      const active = new Set(pointerSlots);
      for (const pad of pads) {
        const flatSlot = Number.parseInt(pad.id.slice(4), 10);
        pad.setAttribute("aria-pressed", active.has(flatSlot) ? "true" : "false");
      }
    }
    renderDiagnostics();
  }

  let pointerAdapter;
  let keyboardAdapter;
  let midiAdapter;

  function pressedCount() {
    return (
      (pointerAdapter?.diagnostics().pressed_count ?? 0) +
      (keyboardAdapter?.diagnostics().pressed_count ?? 0) +
      (midiAdapter?.diagnostics().pressed_note_count ?? 0)
    );
  }

  function diagnostics() {
    const midi = midiAdapter?.diagnostics() ?? {
      permission: "prompt",
      connected_input_count: 0,
    };
    return Object.freeze({
      state: machine.state,
      error_code: lastErrorCode,
      product_build: manifest.product_build,
      host_version: manifest.host_version,
      protocol_version: manifest.protocol_version,
      control_generation: controlGeneration,
      acknowledged_generation: acknowledgedGeneration,
      trigger_admitted_count: triggerAdmittedCount,
      trigger_outcome_count: triggerOutcomeCount,
      trigger_rejected_count: triggerRejectedCount,
      midi_permission: midi.permission,
      connected_input_count: midi.connected_input_count,
      pressed_count: pressedCount(),
    });
  }

  function renderDiagnostics() {
    const stateOutput = element("host-state");
    if (stateOutput) {
      stateOutput.textContent = machine.state;
    }
    const output = element("diagnostics");
    if (output) {
      output.textContent = JSON.stringify(diagnostics(), null, 2);
    }
  }

  function clearPressed() {
    pointerAdapter?.clearPressed();
    keyboardAdapter?.clearPressed();
    midiAdapter?.clearPressed();
    for (const pad of pads) {
      pad.setAttribute("aria-pressed", "false");
    }
    renderDiagnostics();
  }

  function cleanupForTransition(targetState) {
    clearPressed();
    if (targetState === "failed" || targetState === "closed") {
      terminalCleanup();
    }
  }

  const machine = createHostStateMachine({
    notify: () => renderDiagnostics(),
    cleanup: cleanupForTransition,
    sealTake: options.sealTake,
  });

  function terminalCleanup() {
    if (terminalCleanupStarted) {
      return terminalCleanupPromise;
    }
    terminalCleanupStarted = true;
    if (probeReservation?.timeout != null) {
      timers.clearTimeout(probeReservation.timeout);
    }
    probeReservation = null;
    clearPressed();
    unsubscribeTransport?.();
    unsubscribeTransport = null;
    for (const dispose of listenerDisposers.splice(0)) {
      dispose();
    }
    midiAdapter?.dispose();
    terminalCleanupPromise = Promise.resolve()
      .then(() => runtimeTerminator({ runtime, audioContext }))
      .catch(() => {});
    return terminalCleanupPromise;
  }

  function fail(codeOrError) {
    if (machine.state === "failed" || machine.state === "closed") {
      return false;
    }
    lastErrorCode =
      typeof codeOrError === "string"
        ? validatedErrorCode(codeOrError)
        : errorCode(codeOrError);
    closing = true;
    machine.transition("failed", { reason: lastErrorCode });
    renderDiagnostics();
    return true;
  }

  function listen(target, type, listener) {
    if (typeof target?.addEventListener !== "function") {
      return;
    }
    target.addEventListener(type, listener);
    listenerDisposers.push(() => target.removeEventListener(type, listener));
  }

  function boundedRequest(operation, payload) {
    const request = createRequestEnvelope({ operation, payload, crypto });
    const deadlineMs = deadlineForOperation(operation);
    return new Promise((resolvePromise, rejectPromise) => {
      let settled = false;
      const timeout = timers.setTimeout(() => {
        if (!settled) {
          settled = true;
          rejectPromise(typedError("HOST_TIMEOUT", "Host request timed out"));
        }
      }, deadlineMs);
      Promise.resolve(transport.send(request, { deadlineMs })).then(
        (rawResponse) => {
          if (settled) {
            return;
          }
          settled = true;
          timers.clearTimeout(timeout);
          let response;
          try {
            response = validateResponseEnvelope(rawResponse);
          } catch (error) {
            rejectPromise(error);
            return;
          }
          if (response.request_id !== request.request_id) {
            rejectPromise(
              typedError("HOST_PROTOCOL_MISMATCH", "Response request_id mismatch"),
            );
            return;
          }
          if (!response.ok) {
            rejectPromise(
              typedError(response.error.code, "Host request was rejected"),
            );
            return;
          }
          resolvePromise(response.result);
        },
        (error) => {
          if (!settled) {
            settled = true;
            timers.clearTimeout(timeout);
            rejectPromise(error);
          }
        },
      );
    });
  }

  function retainAdmission(sequence, epochId, isProbe) {
    if (!isPositiveInteger(sequence) || admittedSequences.has(sequence)) {
      throw typedError("HOST_PROTOCOL_MISMATCH", "Trigger sequence is invalid");
    }
    if (admittedSequences.size >= TRIGGER_LEDGER_LIMIT) {
      const completed = [...admittedSequences].find(([, entry]) => entry.outcome !== null);
      if (!completed) {
        throw typedError("HOST_STATE_INVALID", "Trigger ledger is full");
      }
      admittedSequences.delete(completed[0]);
    }
    admittedSequences.set(sequence, {
      epochId,
      isProbe,
      outcome: null,
    });
    triggerAdmittedCount += 1;
  }

  function rejectTrigger() {
    triggerRejectedCount += 1;
    renderDiagnostics();
    return false;
  }

  async function trigger(flatSlot, velocity) {
    if (
      !Number.isInteger(flatSlot) ||
      flatSlot < 0 ||
      flatSlot > 63 ||
      !Number.isInteger(velocity) ||
      velocity < 1 ||
      velocity > 127 ||
      closing
    ) {
      return rejectTrigger();
    }

    const ordinary = machine.state === "running";
    const recoveryProbe =
      machine.state === "recovering" &&
      recoveryEpoch !== null &&
      recoveryEpoch.probeWindow === true &&
      probeReservation === null;
    if (!ordinary && !recoveryProbe) {
      return rejectTrigger();
    }

    const admissionEpoch = recoveryProbe ? recoveryEpoch.id : 0;
    if (recoveryProbe) {
      recoveryEpoch.probeWindow = false;
      probeReservation = {
        epochId: admissionEpoch,
        sequence: null,
        timeout: null,
      };
    }

    try {
      const result = await boundedRequest("trigger", {
        slot: flatSlot,
        velocity,
      });
      retainAdmission(result?.sequence, admissionEpoch, recoveryProbe);
      if (recoveryProbe && probeReservation?.epochId === admissionEpoch) {
        probeReservation.sequence = result.sequence;
        probeReservation.timeout = timers.setTimeout(() => {
          if (
            probeReservation?.epochId === admissionEpoch &&
            probeReservation.sequence === result.sequence
          ) {
            fail("HOST_TIMEOUT");
          }
        }, RECOVERY_OUTCOME_DEADLINE_MS);
      }
      renderDiagnostics();
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  async function beginTake(takeId, expectedRevision) {
    if (closing || machine.state !== "running") {
      return false;
    }
    let reserved = false;
    try {
      machine.beginTake(takeId);
      reserved = true;
      await boundedRequest("take.begin", {
        take_id: takeId,
        expected_revision: expectedRevision,
      });
      if (closing || machine.state !== "running") {
        return false;
      }
      return true;
    } catch (error) {
      if (reserved && (closing || machine.state !== "running")) {
        return false;
      }
      fail(error);
      return false;
    }
  }

  function completeRecovery(status) {
    controlGeneration = status?.control_generation ?? null;
    acknowledgedGeneration = status?.acknowledged_generation ?? null;
    if (
      machine.state === "recovering" &&
      recoveryEpoch !== null &&
      audioContext?.state === "running" &&
      generationsMatch(status) &&
      probeReservation === null
    ) {
      recoveryEpoch.contextUsable = true;
      recoveryEpoch.probeWindow = true;
    }
    renderDiagnostics();
  }

  function observeRuntimeStatus(status) {
    if (status === null || typeof status !== "object") {
      fail("HOST_PROTOCOL_MISMATCH");
      return false;
    }
    completeRecovery(status);
    return generationsMatch(status);
  }

  async function activateRuntimeForRecovery(epoch) {
    if (
      recoveryEpoch !== epoch ||
      epoch.activationStarted ||
      machine.state !== "recovering" ||
      audioContext?.state !== "running"
    ) {
      return;
    }
    epoch.activationStarted = true;
    epoch.contextUsable = true;
    try {
      await boundedRequest("audio.activate", {});
      if (recoveryEpoch !== epoch || machine.state !== "recovering") {
        return;
      }
      const status = await boundedRequest("host.status", {});
      if (recoveryEpoch === epoch) {
        completeRecovery(status);
      }
    } catch (error) {
      fail(error);
    }
  }

  function invalidateProbe() {
    if (probeReservation?.timeout != null) {
      timers.clearTimeout(probeReservation.timeout);
    }
    probeReservation = null;
  }

  function beginInterruption(reason) {
    if (closing || machine.state === "failed" || machine.state === "closed") {
      return false;
    }
    clearPressed();

    const isNewRunningEdge = machine.state === "running";
    const isNewRecoveryEdge =
      machine.state === "recovering" && recoveryEpoch?.contextUsable === true;
    if (!isNewRunningEdge && !isNewRecoveryEdge) {
      return false;
    }

    invalidateProbe();
    machine.transition("interrupted", { reason });
    const epoch = {
      id: nextRecoveryEpoch,
      contextUsable: audioContext?.state === "running",
      suspendComplete: false,
      activationStarted: false,
      probeWindow: false,
    };
    nextRecoveryEpoch += 1;
    recoveryEpoch = epoch;

    boundedRequest("audio.suspend", {}).then(
      () => {
        if (recoveryEpoch !== epoch || closing) {
          return;
        }
        epoch.suspendComplete = true;
        if (machine.state === "interrupted") {
          machine.transition("recovering", { reason: "recovery_started" });
        }
        if (audioContext?.state === "running") {
          activateRuntimeForRecovery(epoch);
        } else if (machine.state === "recovering") {
          machine.transition("audio-suspended", {
            reason: "recovery_gesture_required",
          });
        }
      },
      (error) => fail(error),
    );
    return true;
  }

  function markAdverseCondition(condition) {
    const hadActiveCondition = activeAdverseConditions.size > 0;
    activeAdverseConditions.add(condition);
    return !hadActiveCondition;
  }

  function observeContextState() {
    if (!audioContext || closing) {
      return;
    }
    const previousState = lastContextState;
    lastContextState = audioContext.state;
    if (audioContext.state === "running") {
      activeAdverseConditions.delete("audio_statechange");
      if (recoveryEpoch !== null) {
        recoveryEpoch.contextUsable = true;
        if (recoveryEpoch.suspendComplete && machine.state === "recovering") {
          activateRuntimeForRecovery(recoveryEpoch);
        }
      }
      return;
    }
    if (expectedContextSuspend) {
      expectedContextSuspend = false;
      activeAdverseConditions.delete("audio_statechange");
      return;
    }
    if (previousState === audioContext.state) {
      clearPressed();
      return;
    }
    if (markAdverseCondition("audio_statechange")) {
      beginInterruption("audio_statechange");
    } else {
      clearPressed();
    }
  }

  function observeVisibility(hidden) {
    if (hidden === true) {
      if (visibilityHidden) {
        clearPressed();
        return false;
      }
      visibilityHidden = true;
      if (markAdverseCondition("visibilitychange")) {
        beginInterruption("visibilitychange");
      } else {
        clearPressed();
      }
    } else {
      visibilityHidden = false;
      activeAdverseConditions.delete("visibilitychange");
      renderDiagnostics();
    }
  }

  function observePageShow() {
    pageHidden = false;
    activeAdverseConditions.delete("pagehide");
    if (recoveryEpoch?.suspendComplete && machine.state === "recovering") {
      if (audioContext?.state === "running") {
        activateRuntimeForRecovery(recoveryEpoch);
      }
    }
  }

  function observePageHide(event) {
    if (event?.persisted === true) {
      if (pageHidden) {
        clearPressed();
        return Promise.resolve(false);
      }
      pageHidden = true;
      if (markAdverseCondition("pagehide")) {
        beginInterruption("pagehide");
      } else {
        clearPressed();
      }
      return Promise.resolve(false);
    }
    return close();
  }

  function validateOutcome(event) {
    return (
      isPositiveInteger(event?.sequence) &&
      (event.outcome === "voice_started" || event.outcome === "voice_capacity") &&
      Number.isInteger(event.runtime_frame) &&
      event.runtime_frame >= 0
    );
  }

  function observeOutcomes(events) {
    if (!Array.isArray(events) || events.length === 0) {
      fail("HOST_PROTOCOL_MISMATCH");
      return;
    }
    for (const event of events) {
      if (!validateOutcome(event)) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      const admission = admittedSequences.get(event.sequence);
      if (!admission || admission.outcome !== null) {
        fail("HOST_PROTOCOL_MISMATCH");
        return;
      }
      admission.outcome = event.outcome;
      triggerOutcomeCount += 1;

      const isCurrentProbe =
        admission.isProbe &&
        recoveryEpoch !== null &&
        admission.epochId === recoveryEpoch.id &&
        probeReservation?.epochId === recoveryEpoch.id &&
        probeReservation.sequence === event.sequence;
      if (!isCurrentProbe) {
        continue;
      }
      timers.clearTimeout(probeReservation.timeout);
      probeReservation = null;
      if (event.outcome !== "voice_started") {
        fail("HOST_STATE_INVALID");
        return;
      }
      recoveryEpoch = null;
      machine.transition("running", { reason: "recovery_probe_completed" });
    }
    renderDiagnostics();
  }

  function observeNotification(rawNotification) {
    let notification;
    try {
      notification = validateNotificationEnvelope(rawNotification);
    } catch (error) {
      fail(error);
      return;
    }
    if (notification.event === "runtime.trigger_outcomes") {
      observeOutcomes(notification.payload.events);
      return;
    }
    if (
      notification.event === "runtime.warning" &&
      notification.payload?.fatal === true &&
      typeof notification.payload.code === "string"
    ) {
      fail(notification.payload.code);
      return;
    }
    if (notification.event === "snapshot.published") {
      controlGeneration = notification.payload?.generation ?? controlGeneration;
    }
    renderDiagnostics();
  }

  function observeRuntime(observation) {
    if (
      observation?.fatal === true &&
      typeof observation.code === "string" &&
      observation.code.length > 0
    ) {
      fail(observation.code);
      return true;
    }
    return false;
  }

  function activationIsCurrent(reservation, expectedState) {
    return (
      activationReservation === reservation &&
      !closing &&
      !visibilityHidden &&
      !pageHidden &&
      recoveryEpoch === reservation.recoveryEpoch &&
      machine.state === expectedState
    );
  }

  async function activateAudio() {
    if (
      closing ||
      machine.state !== "audio-suspended" ||
      activationReservation !== null ||
      visibilityHidden ||
      pageHidden
    ) {
      return false;
    }
    const reservation = Object.freeze({ recoveryEpoch });
    activationReservation = reservation;
    try {
      if (audioContext === null) {
        audioContext = createAudioContext({ sampleRate: 48_000 });
        lastContextState = audioContext.state;
        listen(audioContext, "statechange", observeContextState);
        contextHandle = runtime.registerAudioContext(audioContext);
        const workletResult = await runtime.startAudioWorklet(contextHandle);
        if (!activationIsCurrent(reservation, "audio-suspended")) {
          return false;
        }
        if (workletResult?.ok === false) {
          throw typedError("HOST_STATE_INVALID", "AudioWorklet start failed");
        }
      }
      await audioContext.resume();
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      if (recoveryEpoch !== null) {
        machine.transition("recovering", {
          reason: "recovery_activation",
          recoveryEpoch: true,
        });
        recoveryEpoch.contextUsable = true;
        recoveryEpoch.suspendComplete = true;
        await activateRuntimeForRecovery(recoveryEpoch);
        if (
          closing ||
          visibilityHidden ||
          pageHidden ||
          recoveryEpoch !== reservation.recoveryEpoch
        ) {
          return false;
        }
        return machine.state === "recovering";
      }
      await boundedRequest("audio.activate", {});
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      const status = await boundedRequest("host.status", {});
      if (!activationIsCurrent(reservation, "audio-suspended")) {
        return false;
      }
      controlGeneration = status?.control_generation ?? null;
      acknowledgedGeneration = status?.acknowledged_generation ?? null;
      if (!generationsMatch(status)) {
        throw typedError(
          "HOST_PROTOCOL_MISMATCH",
          "Initial Runtime generation is not acknowledged",
        );
      }
      machine.transition("running", { reason: "audio_activation" });
      return true;
    } catch (error) {
      if (machine.state !== "failed" && machine.state !== "closed") {
        fail(error);
      }
      return false;
    } finally {
      if (activationReservation === reservation) {
        activationReservation = null;
      }
    }
  }

  async function suspendAudio() {
    if (closing || machine.state !== "running") {
      return false;
    }
    machine.handleOperation("audio.suspend");
    clearPressed();
    expectedContextSuspend = true;
    try {
      await Promise.all([
        boundedRequest("audio.suspend", {}),
        audioContext?.suspend?.() ?? Promise.resolve(),
      ]);
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  async function enableMidi() {
    try {
      await midiAdapter.requestPermission();
      renderDiagnostics();
      return true;
    } catch {
      renderDiagnostics();
      return false;
    }
  }

  async function close() {
    if (closing || machine.state === "closed" || machine.state === "failed") {
      return false;
    }
    closing = true;
    clearPressed();
    invalidateProbe();
    try {
      await boundedRequest("host.close", {});
      machine.transition("closed", { reason: "pagehide" });
      await terminalCleanup();
      return true;
    } catch (error) {
      closing = false;
      fail(error);
      return false;
    }
  }

  function wireInputs() {
    pointerAdapter = createPointerAdapter({
      trigger,
      velocity: options.pointerVelocity ?? 100,
      now: monotonicNow,
      onPressedChange: renderPressed,
    });
    keyboardAdapter = createKeyboardAdapter({
      trigger,
      mapping: options.keyboardMapping ?? defaultKeyboardMapping(),
      velocity: options.keyboardVelocity ?? 100,
      onPressedChange: renderDiagnostics,
    });
    midiAdapter = createMidiAdapter({
      trigger,
      requestMIDIAccess: (...args) => navigator.requestMIDIAccess(...args),
      notify: (event, payload) => {
        if (event === "runtime.warning" && payload?.fatal === true) {
          fail(payload.code);
        }
        renderDiagnostics();
      },
      noteStart: options.midiNoteStart ?? 36,
      slotStart: options.midiSlotStart ?? 0,
      slotCount: options.midiSlotCount ?? 64,
      onPressedChange: renderDiagnostics,
    });

    for (const pad of pads) {
      const projectSlot = Object.freeze({
        bank: Number.parseInt(pad.dataset.bank, 10),
        pad: Number.parseInt(pad.dataset.pad, 10),
      });
      const flatSlot = flattenPadSlot(projectSlot);
      listen(pad, "pointerdown", (event) =>
        pointerAdapter.pointerDown(event, flatSlot));
      listen(pad, "mousedown", (event) =>
        pointerAdapter.mouseDown(event, flatSlot));
      listen(pad, "pointerup", (event) => {
        if (!pointerAdapter.releasePointer(event)) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "mouseup", (event) => {
        if (!pointerAdapter.releaseMouse(event)) {
          pointerAdapter.pointerUp(event, flatSlot);
        }
      });
      listen(pad, "pointercancel", (event) => {
        pointerAdapter.pointerCancel(event);
        pointerAdapter.pointerUp(event, flatSlot);
      });
    }
    listen(window, "pointerup", (event) => pointerAdapter.releasePointer(event));
    listen(window, "pointercancel", (event) => pointerAdapter.pointerCancel(event));
    listen(window, "mouseup", (event) => pointerAdapter.releaseMouse(event));
    listen(window, "blur", () => pointerAdapter.clearPressed());
    listen(window, "keydown", (event) => keyboardAdapter.keyDown(event));
    listen(window, "keyup", (event) => keyboardAdapter.keyUp(event));
    listen(element("audio-activate"), "click", () => activateAudio());
    listen(element("audio-suspend"), "click", () => suspendAudio());
    listen(element("midi-enable"), "click", () => enableMidi());
  }

  function wireLifecycle() {
    listen(document, "visibilitychange", () =>
      observeVisibility(document.visibilityState === "hidden"));
    listen(window, "pagehide", (event) => observePageHide(event));
    listen(window, "pageshow", observePageShow);
    for (const worker of runtime?.workers ?? []) {
      listen(worker, "error", () => fail("HOST_STATE_INVALID"));
      listen(worker, "messageerror", () => fail("HOST_PROTOCOL_MISMATCH"));
    }
    if (runtime?.worklet) {
      listen(runtime.worklet, "processorerror", () =>
        fail("HOST_STATE_INVALID"));
    }
    if (typeof transport.subscribe === "function") {
      unsubscribeTransport = transport.subscribe(observeNotification);
    }
  }

  async function start() {
    if (started) {
      return false;
    }
    started = true;
    try {
      machine.transition("preflight", { reason: "bootstrap" });
      await runPreflight(options.capabilities ?? defaultCapabilities(window));
      manifest = Object.freeze(await verifyManifest());
      if (
        typeof manifest.product_build !== "string" ||
        typeof manifest.host_version !== "string" ||
        manifest.protocol_version !== 1
      ) {
        throw typedError("HOST_PROTOCOL_MISMATCH", "Manifest identity is invalid");
      }
      runtime = await loadRuntime(manifest);
      machine.transition("storage-ready", { reason: "runtime_loaded" });
      machine.transition("core-ready", { reason: "runtime_ready" });
      machine.transition("audio-suspended", { reason: "activation_required" });
      wireInputs();
      wireLifecycle();
      renderDiagnostics();
      return true;
    } catch (error) {
      fail(error);
      return false;
    }
  }

  return Object.freeze({
    start,
    trigger,
    beginTake,
    activateAudio,
    suspendAudio,
    enableMidi,
    close,
    observeVisibility,
    observePageHide,
    observePageShow,
    observeRuntimeStatus,
    observeRuntime,
    handleKeyDown(event) {
      return keyboardAdapter?.keyDown(event) ?? false;
    },
    diagnostics,
    get state() {
      return machine.state;
    },
  });
}

if (typeof window !== "undefined" && typeof document !== "undefined") {
  const controller = createWebRuntimeHostController({
    document,
    window,
    ...window.__LMDJ_WEB_HOST_SEAMS__,
  });
  window.lmdjWebRuntimeController = controller;
  controller.start();
}
