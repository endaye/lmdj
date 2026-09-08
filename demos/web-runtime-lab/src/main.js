import { createReport, preflight } from "./probe-core.mjs";
import {
  BROWSER_RUN_TARGETS,
  canDispatchBrowserTrigger,
  evaluateBrowserRunGuidance,
  isEligiblePhysicalRoute,
} from "./physical-run-guidance.mjs";

const HEADER_LENGTH = 8;
const RING_CAPACITY = 1024;
const RECORD_LENGTH = 3;

const WRITE_INDEX = 0;
const READ_INDEX = 1;
const ACK_COUNT = 2;
const PROCESS_CALLS = 3;
const LAST_QUANTUM = 4;
const DROPPED_COUNT = 5;

const SOURCE_POINTER = 1;
const SOURCE_MIDI = 2;
const SOURCE_OFFSET = 0;
const NOTE_OFFSET = 1;
const VELOCITY_OFFSET = 2;

const INITIAL_DECISION = Object.freeze({
  decisionStatus: "threshold-approved",
});

const byId = (id) => document.getElementById(id);
const startButton = byId("start-audio");
const triggerButton = byId("trigger-pad");
const midiButton = byId("enable-midi");
const suspendButton = byId("suspend-audio");
const resumeButton = byId("resume-audio");
const exportButton = byId("export-report");
const routeCategory = byId("route-category");
const runGuidanceOutput = byId("run-guidance-output");

const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
const capabilities = {
  secureContext: window.isSecureContext,
  crossOriginIsolated: window.crossOriginIsolated,
  sharedArrayBuffer: typeof SharedArrayBuffer === "function",
  atomics: typeof Atomics === "object",
  audioContext: typeof AudioContextConstructor === "function",
  audioWorkletNode: typeof AudioWorkletNode === "function",
  webAssembly: typeof WebAssembly === "object",
};
const readiness = preflight(capabilities);

const session = {
  sessionId: crypto.randomUUID(),
  startedAt: new Date().toISOString(),
  endedAt: new Date().toISOString(),
  environment: {
    userAgent: navigator.userAgent,
    platform: navigator.platform || "unavailable",
    language: navigator.language,
    routeCategory: routeCategory.value,
  },
  capabilities,
  audioContext: {
    state: "not-started",
    sampleRate: 0,
    baseLatency: null,
    outputLatency: null,
    observedQuantumSizes: [],
    lastOutputTimestamp: null,
  },
  wasm: { ready: false, calls: 0 },
  sharedControl: {
    dispatchedCount: 0,
    acknowledgedCount: 0,
    duplicateAcknowledgements: 0,
    droppedCount: 0,
  },
  midi: {
    supported: typeof navigator.requestMIDIAccess === "function",
    permission: "not-requested",
    inputCount: 0,
    eventCount: 0,
    lastNote: null,
    lastVelocity: null,
  },
  lifecycle: [],
  triggerDispatches: [],
  triggerAcknowledgements: [],
  browserRun: {
    startedAtMs: null,
    interrupted: false,
  },
  errors: [],
  ...INITIAL_DECISION,
};

let audioContext = null;
let controlView = null;
let workletNode = null;
let midiAccess = null;
const attachedMidiInputs = new WeakSet();
const pendingTriggers = new Map();
const observedQuantumSizes = new Set();


function recordLifecycle(type, state) {
  session.lifecycle.push({ type, state, atMs: performance.now() });
  render();
}


function interruptBrowserRun() {
  if (session.browserRun.startedAtMs !== null) {
    session.browserRun.interrupted = true;
  }
}


function formatDuration(durationMs) {
  const totalSeconds = Math.floor(durationMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}


function browserRunGuidance() {
  const pendingTimes = [...pendingTriggers.values()].map(
    ({ eventAtMs }) => eventAtMs,
  );
  return evaluateBrowserRunGuidance({
    startedAtMs: session.browserRun.startedAtMs,
    nowMs: performance.now(),
    dispatchedCount: session.sharedControl.dispatchedCount,
    acknowledgedCount: session.sharedControl.acknowledgedCount,
    duplicateAcknowledgements: session.sharedControl.duplicateAcknowledgements,
    droppedCount: session.sharedControl.droppedCount,
    processorErrors: session.errors.filter((error) => (
      error.toLowerCase().includes("processorerror")
    )).length,
    oldestPendingAtMs: pendingTimes.length === 0
      ? null
      : Math.min(...pendingTimes),
    audioState: session.audioContext.state,
    visibilityState: document.visibilityState,
    interrupted: session.browserRun.interrupted,
  });
}


function syncAudioContext() {
  if (!audioContext) {
    return;
  }
  session.audioContext.state = audioContext.state;
  session.audioContext.sampleRate = audioContext.sampleRate;
  session.audioContext.baseLatency = Number.isFinite(audioContext.baseLatency)
    ? audioContext.baseLatency
    : null;
  session.audioContext.outputLatency = Number.isFinite(audioContext.outputLatency)
    ? audioContext.outputLatency
    : null;
  session.audioContext.observedQuantumSizes = [...observedQuantumSizes]
    .sort((left, right) => left - right);
  if (typeof audioContext.getOutputTimestamp === "function") {
    const timestamp = audioContext.getOutputTimestamp();
    if (
      Number.isFinite(timestamp.contextTime)
      && Number.isFinite(timestamp.performanceTime)
    ) {
      session.audioContext.lastOutputTimestamp = {
        contextTime: timestamp.contextTime,
        performanceTime: timestamp.performanceTime,
      };
    }
  }
}


function syncSharedControl() {
  if (!controlView) {
    return;
  }
  session.sharedControl.droppedCount = Atomics.load(
    controlView,
    DROPPED_COUNT,
  );
  session.wasm.calls = Atomics.load(controlView, PROCESS_CALLS);
  const quantum = Atomics.load(controlView, LAST_QUANTUM);
  if (quantum > 0) {
    observedQuantumSizes.add(quantum);
  }
}


function render() {
  syncSharedControl();
  syncAudioContext();
  const missing = readiness.missing.length === 0
    ? "none"
    : readiness.missing.join(", ");
  byId("preflight-output").textContent = readiness.ready
    ? "Ready: secure and cross-origin isolated"
    : `Unavailable: ${missing}`;
  byId("audio-output").textContent = [
    `state: ${session.audioContext.state}`,
    `sampleRate: ${session.audioContext.sampleRate || "—"}`,
    `baseLatency: ${session.audioContext.baseLatency ?? "—"}`,
    `outputLatency: ${session.audioContext.outputLatency ?? "—"}`,
  ].join("\n");
  byId("runtime-output").textContent = [
    `WASM ready: ${session.wasm.ready}`,
    `processor calls: ${session.wasm.calls}`,
    `quantum sizes: ${session.audioContext.observedQuantumSizes.join(", ") || "—"}`,
  ].join("\n");
  byId("control-output").textContent = [
    `dispatched: ${session.sharedControl.dispatchedCount}`,
    `acknowledged: ${session.sharedControl.acknowledgedCount}`,
    `duplicates: ${session.sharedControl.duplicateAcknowledgements}`,
    `ring-full drops: ${session.sharedControl.droppedCount}`,
  ].join("\n");
  byId("midi-output").textContent = [
    `supported: ${session.midi.supported}`,
    `permission: ${session.midi.permission}`,
    `inputs: ${session.midi.inputCount}`,
    `events: ${session.midi.eventCount}`,
  ].join("\n");
  const values = session.triggerAcknowledgements.map(
    (record) => record.acknowledgementAtMs - record.eventAtMs,
  );
  byId("estimate-output").textContent = values.length === 0
    ? "No browser estimates yet"
    : `latest event-to-ack: ${values.at(-1).toFixed(2)} ms\nrecords: ${values.length}`;
  byId("lifecycle-output").textContent = session.lifecycle.length === 0
    ? "No transitions recorded"
    : session.lifecycle.slice(-6).map(
      (event) => `${event.type}: ${event.state} @ ${event.atMs.toFixed(1)} ms`,
    ).join("\n");
  byId("error-output").textContent = session.errors.length === 0
    ? "none"
    : session.errors.slice(-6).join("\n");
  const guidance = browserRunGuidance();
  const guidanceDetail = guidance.status === "not-started"
    ? "Select an eligible route, then start audio once."
    : guidance.status === "restart-required"
      ? `Reload before recording: ${guidance.reasons.join(", ")}`
      : guidance.status === "browser-target-ready"
        ? "Browser target ready. Export the report and retain the external capture."
        : "Keep this page visible and AudioContext running.";
  runGuidanceOutput.textContent = [
    `status: ${guidance.status}`,
    `triggers: ${session.sharedControl.dispatchedCount} / ${BROWSER_RUN_TARGETS.triggerCount}`,
    `foreground: ${formatDuration(guidance.elapsedMs)} / ${formatDuration(BROWSER_RUN_TARGETS.foregroundDurationMs)}`,
    guidanceDetail,
    "240 fps-or-faster video or calibrated wired-loopback evidence is still required.",
  ].join("\n");

  const running = audioContext?.state === "running";
  startButton.disabled = !readiness.ready
    || audioContext !== null
    || !isEligiblePhysicalRoute(routeCategory.value);
  triggerButton.disabled = !running
    || !session.wasm.ready
    || session.sharedControl.dispatchedCount >= BROWSER_RUN_TARGETS.triggerCount;
  midiButton.disabled = !running || !session.midi.supported;
  suspendButton.disabled = !running;
  resumeButton.disabled = !audioContext || running;
  exportButton.disabled = !audioContext;
}


function enqueueTrigger(source, note, velocity, pointerType = "pointer") {
  if (!controlView || audioContext?.state !== "running") {
    return false;
  }
  if (!canDispatchBrowserTrigger(session.sharedControl.dispatchedCount)) {
    return false;
  }
  const writeIndex = Atomics.load(controlView, WRITE_INDEX);
  const readIndex = Atomics.load(controlView, READ_INDEX);
  if (writeIndex - readIndex >= RING_CAPACITY) {
    Atomics.add(controlView, DROPPED_COUNT, 1);
    session.errors.push(`ring-full at ${performance.now().toFixed(1)} ms`);
    render();
    return false;
  }

  const recordOffset = HEADER_LENGTH
    + (writeIndex % RING_CAPACITY) * RECORD_LENGTH;
  const sequence = writeIndex + 1;
  const eventAtMs = performance.now();
  const resolvedSource = source === SOURCE_MIDI
    ? "midi"
    : pointerType === "touch"
      ? "touch"
      : "pointer";
  Atomics.store(controlView, recordOffset + SOURCE_OFFSET, source);
  Atomics.store(controlView, recordOffset + NOTE_OFFSET, note);
  Atomics.store(controlView, recordOffset + VELOCITY_OFFSET, velocity);
  session.triggerDispatches.push({
    sequence,
    source: resolvedSource,
    note,
    velocity,
    eventAtMs,
  });
  pendingTriggers.set(sequence, {
    eventAtMs,
    source: resolvedSource,
    note,
    velocity,
  });
  Atomics.add(controlView, WRITE_INDEX, 1);
  session.sharedControl.dispatchedCount += 1;
  render();
  return true;
}


function handleAcknowledgement(message) {
  const pending = pendingTriggers.get(message.sequence);
  if (!pending) {
    session.sharedControl.duplicateAcknowledgements += 1;
    session.errors.push(`unexpected acknowledgement ${message.sequence}`);
    render();
    return;
  }
  pendingTriggers.delete(message.sequence);
  const acknowledgementAtMs = performance.now();
  session.triggerAcknowledgements.push({
    sequence: message.sequence,
    source: pending.source,
    note: pending.note,
    velocity: pending.velocity,
    eventAtMs: pending.eventAtMs,
    acknowledgementAtMs,
    renderFrame: message.renderFrame,
    contextTime: message.contextTime,
    quantumSize: message.quantumSize,
  });
  session.sharedControl.acknowledgedCount += 1;
  session.wasm.calls = message.processorCalls;
  observedQuantumSizes.add(message.quantumSize);
  render();
}


async function startAudio() {
  if (
    !readiness.ready
    || audioContext
    || !isEligiblePhysicalRoute(routeCategory.value)
  ) {
    return;
  }
  audioContext = new AudioContextConstructor({ latencyHint: "interactive" });
  audioContext.addEventListener("statechange", () => {
    if (
      session.browserRun.startedAtMs !== null
      && audioContext.state !== "running"
    ) {
      interruptBrowserRun();
    }
    recordLifecycle("audio-state", audioContext.state);
  });
  await audioContext.audioWorklet.addModule("./src/worklet.js");
  const control = new SharedArrayBuffer(
    Int32Array.BYTES_PER_ELEMENT
      * (HEADER_LENGTH + RING_CAPACITY * RECORD_LENGTH),
  );
  controlView = new Int32Array(control);
  workletNode = new AudioWorkletNode(
    audioContext,
    "lmdj-web-runtime-probe",
    {
      processorOptions: {
        control,
        headerLength: HEADER_LENGTH,
        ringCapacity: RING_CAPACITY,
        recordLength: RECORD_LENGTH,
      },
    },
  );
  workletNode.addEventListener("processorerror", () => {
    session.errors.push("AudioWorklet processorerror");
    render();
  });
  workletNode.port.addEventListener("message", (event) => {
    if (event.data?.type === "wasm-ready") {
      session.wasm.ready = true;
      render();
    } else if (event.data?.type === "acknowledgement") {
      handleAcknowledgement(event.data);
    }
  });
  workletNode.port.start();
  workletNode.connect(audioContext.destination);
  await audioContext.resume();
  if (audioContext.state === "running") {
    session.browserRun.startedAtMs = performance.now();
  }
  recordLifecycle("audio-state", audioContext.state);
  render();
}


function onMidiMessage(event) {
  const data = event.data;
  if (!data || data.length < 3) {
    return;
  }
  const command = data[0] & 0xf0;
  const note = data[1];
  const velocity = data[2];
  if (command !== 0x90 || velocity === 0) {
    return;
  }
  session.midi.eventCount += 1;
  session.midi.lastNote = note;
  session.midi.lastVelocity = velocity;
  enqueueTrigger(SOURCE_MIDI, note, velocity);
}


function attachMidiInputs() {
  if (!midiAccess) {
    return;
  }
  session.midi.inputCount = midiAccess.inputs.size;
  for (const input of midiAccess.inputs.values()) {
    if (!attachedMidiInputs.has(input)) {
      input.addEventListener("midimessage", onMidiMessage);
      attachedMidiInputs.add(input);
    }
  }
  render();
}


async function enableMidi() {
  try {
    midiAccess = await navigator.requestMIDIAccess({ sysex: false });
    session.midi.permission = "granted";
    midiAccess.addEventListener("statechange", attachMidiInputs);
    attachMidiInputs();
  } catch (error) {
    session.midi.permission = "denied-or-error";
    session.errors.push(`MIDI permission: ${String(error)}`);
    render();
  }
}


function exportReport() {
  session.endedAt = new Date().toISOString();
  session.environment.routeCategory = routeCategory.value;
  syncSharedControl();
  syncAudioContext();
  try {
    const report = createReport(session);
    const blob = new Blob([`${JSON.stringify(report, null, 2)}\n`], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `web-runtime-lab-${session.sessionId}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  } catch (error) {
    session.errors.push(`report export: ${String(error)}`);
    render();
  }
}


startButton.addEventListener("click", async () => {
  startButton.disabled = true;
  try {
    await startAudio();
  } catch (error) {
    session.errors.push(`audio start: ${String(error)}`);
  }
  render();
});
triggerButton.addEventListener("pointerdown", (event) => {
  enqueueTrigger(SOURCE_POINTER, 36, 100, event.pointerType);
});
midiButton.addEventListener("click", enableMidi);
suspendButton.addEventListener("click", async () => {
  await audioContext?.suspend();
  render();
});
resumeButton.addEventListener("click", async () => {
  await audioContext?.resume();
  render();
});
exportButton.addEventListener("click", exportReport);
routeCategory.addEventListener("change", () => {
  interruptBrowserRun();
  session.environment.routeCategory = routeCategory.value;
  render();
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") {
    interruptBrowserRun();
  }
  recordLifecycle("visibility", document.visibilityState);
});
window.addEventListener("pagehide", () => {
  interruptBrowserRun();
  recordLifecycle("pagehide", document.visibilityState);
});
window.addEventListener("pageshow", () => {
  recordLifecycle("pageshow", document.visibilityState);
});
document.addEventListener("freeze", () => {
  interruptBrowserRun();
  recordLifecycle("freeze", document.visibilityState);
});
document.addEventListener("resume", () => {
  recordLifecycle("resume", document.visibilityState);
});

byId("decision-status").textContent = (
  "Threshold approved · physical gate unverified"
);
render();
window.setInterval(render, 1000);
