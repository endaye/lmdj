import { REQUIRED_ROWS } from "./physical-gate.mjs";


const ELIGIBLE_ROUTES = new Set(["built-in", "wired"]);
const CAPABILITY_KEYS = Object.freeze([
  "secureContext",
  "crossOriginIsolated",
  "sharedArrayBuffer",
  "atomics",
  "audioContext",
  "audioWorkletNode",
  "webAssembly",
]);
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;


function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}


function nonEmptyString(value, label) {
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new TypeError(`${label} must be a non-empty string`);
  }
  return value;
}


function nonNegativeNumber(value, label) {
  if (!Number.isFinite(value) || value < 0) {
    throw new TypeError(`${label} must be finite and non-negative`);
  }
  return value;
}


function positiveInteger(value, label) {
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new TypeError(`${label} must be a positive safe integer`);
  }
  return value;
}


function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative safe integer`);
  }
  return value;
}


function nullableNonNegative(value, label) {
  return value === null ? null : nonNegativeNumber(value, label);
}


function requiredRow(rowKey) {
  const row = REQUIRED_ROWS.find(({ key }) => key === rowKey);
  if (row === undefined) {
    throw new RangeError("rowKey must identify a required row");
  }
  return row;
}


function validateReportEnvelope(report, options) {
  if (!isObject(report)) {
    throw new TypeError("browser report must be an object");
  }
  if (report.reportVersion !== 2) {
    throw new RangeError("browser report must use reportVersion 2");
  }
  if (report.decisionStatus !== "threshold-approved") {
    throw new RangeError("browser report threshold must be approved");
  }
  if (report.physicalMeasurement !== null) {
    throw new TypeError("browser report physicalMeasurement must be null");
  }
  if (!UUID_V4.test(nonEmptyString(report.sessionId, "sessionId"))) {
    throw new TypeError("sessionId must be a random v4 UUID");
  }
  const recordedAt = nonEmptyString(report.endedAt, "endedAt");
  if (!recordedAt.endsWith("Z") || !Number.isFinite(Date.parse(recordedAt))) {
    throw new TypeError("endedAt must be a UTC timestamp");
  }
  nonEmptyString(options?.osVersion, "osVersion");
  nonEmptyString(options?.browserVersion, "browserVersion");
}


function prepareEnvironment(report, row, options) {
  if (!isObject(report.environment)) {
    throw new TypeError("browser report environment must be an object");
  }
  const routeCategory = nonEmptyString(
    report.environment.routeCategory,
    "routeCategory",
  );
  if (!ELIGIBLE_ROUTES.has(routeCategory)) {
    throw new RangeError("routeCategory must be built-in or wired");
  }
  const sampleRate = nonNegativeNumber(
    report.audioContext?.sampleRate,
    "sampleRate",
  );
  if (sampleRate === 0) {
    throw new RangeError("sampleRate must be positive");
  }
  return {
    platform: row.platform,
    browser: row.browser,
    osVersion: options.osVersion,
    browserVersion: options.browserVersion,
    deviceClass: row.deviceClass,
    inputSource: row.inputSource,
    routeCategory,
    sampleRate,
  };
}


function prepareRuntime(report) {
  if (!isObject(report.audioContext) || !isObject(report.wasm)) {
    throw new TypeError("browser report runtime evidence is missing");
  }
  if (report.wasm.ready !== true) {
    throw new TypeError("browser report WASM must be ready");
  }
  const stateHistory = Array.isArray(report.lifecycle)
    ? report.lifecycle.filter(({ type }) => type === "audio-state").map(
      ({ state, atMs }) => ({
        state: nonEmptyString(state, "audio state"),
        atMs: nonNegativeNumber(atMs, "audio state time"),
      }),
    )
    : [];
  if (!stateHistory.some(({ state }) => state === "running")) {
    throw new TypeError("browser report must retain a running AudioContext state");
  }
  const observedQuantumSizes = report.audioContext.observedQuantumSizes;
  if (
    !Array.isArray(observedQuantumSizes)
    || observedQuantumSizes.length === 0
  ) {
    throw new TypeError("observedQuantumSizes must be non-empty");
  }
  const quantumSizes = observedQuantumSizes.map((size) => (
    positiveInteger(size, "observed quantum size")
  ));
  if (new Set(quantumSizes).size !== quantumSizes.length) {
    throw new TypeError("observedQuantumSizes must be unique");
  }
  return {
    audioContextStateHistory: stateHistory,
    baseLatency: nullableNonNegative(
      report.audioContext.baseLatency,
      "baseLatency",
    ),
    outputLatency: nullableNonNegative(
      report.audioContext.outputLatency,
      "outputLatency",
    ),
    observedQuantumSizes: quantumSizes,
    processorCallbackCount: positiveInteger(
      report.wasm.calls,
      "processor callback count",
    ),
  };
}


function prepareDiagnostics(report) {
  if (!Array.isArray(report.errors) || report.errors.some(
    (error) => typeof error !== "string",
  )) {
    throw new TypeError("browser report errors must be an array of strings");
  }
  if (!isObject(report.capabilities)) {
    throw new TypeError("browser report capabilities must be an object");
  }
  const unsupportedCapabilities = [];
  for (const capability of CAPABILITY_KEYS) {
    if (typeof report.capabilities[capability] !== "boolean") {
      throw new TypeError(`capability ${capability} must be boolean`);
    }
    if (!report.capabilities[capability]) {
      unsupportedCapabilities.push(capability);
    }
  }
  return {
    errors: [...report.errors],
    unsupportedCapabilities,
  };
}


function preparePerformance(report, row) {
  const dispatches = report.triggerDispatches;
  if (!Array.isArray(dispatches) || dispatches.length !== 500) {
    throw new RangeError("performance report must contain exactly 500 dispatches");
  }
  if (!Array.isArray(report.browserEstimates?.records)) {
    throw new TypeError("browser acknowledgement records must be an array");
  }
  const acknowledgements = new Map();
  for (const acknowledgement of report.browserEstimates.records) {
    if (!isObject(acknowledgement)) {
      throw new TypeError("browser acknowledgement record is invalid");
    }
    const sequence = positiveInteger(
      acknowledgement.sequence,
      "acknowledgement sequence",
    );
    if (acknowledgements.has(sequence)) {
      throw new TypeError("acknowledgement sequences must be unique");
    }
    acknowledgements.set(sequence, acknowledgement);
  }

  const sequences = new Set();
  const triggerRecords = dispatches.map((dispatch) => {
    if (!isObject(dispatch)) {
      throw new TypeError("browser dispatch record is invalid");
    }
    const sequence = positiveInteger(dispatch.sequence, "dispatch sequence");
    if (sequences.has(sequence)) {
      throw new TypeError("dispatch sequences must be unique");
    }
    sequences.add(sequence);
    if (dispatch.source !== row.inputSource) {
      throw new TypeError(`dispatch source ${row.inputSource} is required`);
    }
    const eventAtMs = nonNegativeNumber(dispatch.eventAtMs, "dispatch time");
    const acknowledgement = acknowledgements.get(sequence);
    if (acknowledgement === undefined) {
      return {
        sequence,
        source: row.inputSource,
        eventAtMs,
        acknowledgementAtMs: null,
        quantumSize: null,
      };
    }
    if (
      acknowledgement.source !== row.inputSource
      || acknowledgement.eventAtMs !== eventAtMs
    ) {
      throw new TypeError("acknowledgement does not match dispatch");
    }
    const acknowledgementAtMs = nonNegativeNumber(
      acknowledgement.acknowledgementAtMs,
      "acknowledgement time",
    );
    if (acknowledgementAtMs < eventAtMs) {
      throw new RangeError("acknowledgement time precedes dispatch");
    }
    return {
      sequence,
      source: row.inputSource,
      eventAtMs,
      acknowledgementAtMs,
      quantumSize: positiveInteger(
        acknowledgement.quantumSize,
        "acknowledgement quantum size",
      ),
    };
  });
  if ([...acknowledgements.keys()].some((sequence) => !sequences.has(sequence))) {
    throw new TypeError("acknowledgement has no matching dispatch");
  }

  const summary = report.triggerSummary;
  const shared = report.sharedControl;
  if (!isObject(summary) || !isObject(shared)) {
    throw new TypeError("browser trigger counts are missing");
  }
  const acknowledgedCount = acknowledgements.size;
  const missedAcknowledgements = 500 - acknowledgedCount;
  if (
    summary.dispatchedCount !== 500
    || summary.acknowledgedCount !== acknowledgedCount
    || summary.missedAcknowledgements !== missedAcknowledgements
    || shared.dispatchedCount !== 500
    || shared.acknowledgedCount !== acknowledgedCount
  ) {
    throw new TypeError("browser trigger counts do not match records");
  }
  const duplicateAcknowledgements = nonNegativeInteger(
    summary.duplicateAcknowledgements,
    "duplicate acknowledgements",
  );
  if (shared.duplicateAcknowledgements !== duplicateAcknowledgements) {
    throw new TypeError("duplicate acknowledgement counts do not match");
  }

  if (row.requiresMidiAcknowledgements) {
    if (
      report.midi?.supported !== true
      || report.midi?.permission !== "granted"
      || !Number.isSafeInteger(report.midi?.inputCount)
      || report.midi.inputCount <= 0
      || !Number.isSafeInteger(report.midi?.eventCount)
      || report.midi.eventCount < 500
    ) {
      throw new TypeError("MIDI row requires granted physical MIDI evidence");
    }
  }

  const prepared = {
    triggerRecords,
    physical: {
      method: null,
      captureRateHz: null,
      calibrationOffsetMs: null,
      triggerCount: 500,
      p50Ms: null,
      p95Ms: null,
      p99Ms: null,
      missedOnsets: null,
      duplicateOnsets: null,
    },
  };
  if (row.requiresForeground) {
    prepared.foreground = {
      durationMs: null,
      underruns: null,
      processorErrors: report.errors.filter((error) => (
        error.toLowerCase().includes("processorerror")
      )).length,
      lostAcknowledgements: missedAcknowledgements,
      duplicateAcknowledgements,
    };
  }
  if (row.requiresMidiAcknowledgements) {
    prepared.acknowledgements = {
      triggerCount: 500,
      acknowledgedCount,
      lostAcknowledgements: missedAcknowledgements,
      duplicateAcknowledgements,
    };
  }
  return prepared;
}


export function preparePhysicalEvidence(rowKey, report, options) {
  const row = requiredRow(rowKey);
  validateReportEnvelope(report, options);
  const environment = prepareEnvironment(report, row, options);
  const runtime = prepareRuntime(report);
  const diagnostics = prepareDiagnostics(report);
  const run = {
    key: row.key,
    sessionId: report.sessionId,
    recordedAt: report.endedAt,
    environment,
    runtime,
    ...diagnostics,
  };
  if (row.kind === "performance") {
    Object.assign(run, preparePerformance(report, row));
  } else {
    run.lifecycle = {
      actions: [],
      recoverySamplesMs: [],
      maxExplicitActivations: null,
      postRecoveryMissedOnsets: null,
      postRecoveryDuplicateOnsets: null,
    };
  }
  return { evidenceVersion: 1, runs: [run] };
}
