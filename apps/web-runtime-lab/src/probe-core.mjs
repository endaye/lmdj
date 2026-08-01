const PREFLIGHT_KEYS = Object.freeze([
  "secureContext",
  "crossOriginIsolated",
  "sharedArrayBuffer",
  "atomics",
  "audioContext",
  "audioWorkletNode",
  "webAssembly",
]);


function finiteNonNegative(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`${label} must be finite`);
  }
  if (value < 0) {
    throw new RangeError(`${label} must be non-negative`);
  }
  return value;
}


function nonNegativeInteger(value, label) {
  finiteNonNegative(value, label);
  if (!Number.isSafeInteger(value)) {
    throw new TypeError(`${label} must be a safe integer`);
  }
  return value;
}


function optionalFiniteNonNegative(value, label) {
  return value == null ? null : finiteNonNegative(value, label);
}


function requiredString(value, label) {
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${label} must be a non-empty string`);
  }
  return value;
}


function booleanValue(value, label) {
  if (typeof value !== "boolean") {
    throw new TypeError(`${label} must be boolean`);
  }
  return value;
}


export function preflight(capabilities) {
  const missing = PREFLIGHT_KEYS.filter(
    (capability) => capabilities?.[capability] !== true,
  );
  return {
    ready: missing.length === 0,
    missing,
  };
}


export function percentile(values, percentileValue) {
  if (!Array.isArray(values) || values.length === 0) {
    throw new TypeError("percentile values must be a non-empty array");
  }
  if (!Number.isFinite(percentileValue)) {
    throw new TypeError("percentile must be finite");
  }
  if (percentileValue <= 0) {
    throw new RangeError("percentile must be greater than zero");
  }
  if (percentileValue > 1) {
    throw new RangeError("percentile must be at most one");
  }
  const sorted = values.map((value, index) =>
    finiteNonNegative(value, `percentile value ${index}`),
  ).sort((left, right) => left - right);
  const rank = Math.ceil(percentileValue * sorted.length);
  return sorted[rank - 1];
}


function capabilitiesReport(capabilities) {
  return Object.fromEntries(PREFLIGHT_KEYS.map((key) => [
    key,
    capabilities?.[key] === true,
  ]));
}


function environmentReport(environment) {
  return {
    userAgent: requiredString(environment?.userAgent, "userAgent"),
    platform: requiredString(environment?.platform, "platform"),
    language: requiredString(environment?.language, "language"),
    routeCategory: requiredString(
      environment?.routeCategory,
      "routeCategory",
    ),
  };
}


function audioContextReport(audioContext) {
  const observedQuantumSizes = audioContext?.observedQuantumSizes;
  if (!Array.isArray(observedQuantumSizes)) {
    throw new TypeError("observedQuantumSizes must be an array");
  }
  return {
    state: requiredString(audioContext?.state, "audioContext state"),
    sampleRate: finiteNonNegative(
      audioContext?.sampleRate,
      "audioContext sampleRate",
    ),
    baseLatency: optionalFiniteNonNegative(
      audioContext?.baseLatency,
      "audioContext baseLatency",
    ),
    outputLatency: optionalFiniteNonNegative(
      audioContext?.outputLatency,
      "audioContext outputLatency",
    ),
    observedQuantumSizes: [
      ...new Set(observedQuantumSizes.map((value, index) =>
        nonNegativeInteger(value, `observed quantum size ${index}`),
      )),
    ].sort((left, right) => left - right),
  };
}


function wasmReport(wasm) {
  return {
    ready: booleanValue(wasm?.ready, "wasm ready"),
    calls: nonNegativeInteger(wasm?.calls, "wasm calls"),
  };
}


function sharedControlReport(sharedControl) {
  return {
    dispatchedCount: nonNegativeInteger(
      sharedControl?.dispatchedCount,
      "dispatched count",
    ),
    acknowledgedCount: nonNegativeInteger(
      sharedControl?.acknowledgedCount,
      "acknowledged count",
    ),
    duplicateAcknowledgements: nonNegativeInteger(
      sharedControl?.duplicateAcknowledgements,
      "duplicate acknowledgements",
    ),
  };
}


function midiReport(midi) {
  return {
    supported: booleanValue(midi?.supported, "midi supported"),
    permission: requiredString(midi?.permission, "midi permission"),
    inputCount: nonNegativeInteger(midi?.inputCount, "midi input count"),
    eventCount: nonNegativeInteger(midi?.eventCount, "midi event count"),
    lastNote: midi?.lastNote == null
      ? null
      : nonNegativeInteger(midi.lastNote, "midi last note"),
    lastVelocity: midi?.lastVelocity == null
      ? null
      : nonNegativeInteger(midi.lastVelocity, "midi last velocity"),
  };
}


function lifecycleReport(lifecycle) {
  if (!Array.isArray(lifecycle)) {
    throw new TypeError("lifecycle must be an array");
  }
  return lifecycle.map((event, index) => ({
    type: requiredString(event?.type, `lifecycle ${index} type`),
    state: requiredString(event?.state, `lifecycle ${index} state`),
    atMs: finiteNonNegative(event?.atMs, `lifecycle ${index} atMs`),
  }));
}


function acknowledgementEstimates(acknowledgements) {
  if (!Array.isArray(acknowledgements)) {
    throw new TypeError("triggerAcknowledgements must be an array");
  }
  const acknowledgementMs = acknowledgements.map((acknowledgement, index) => {
    const eventAtMs = finiteNonNegative(
      acknowledgement?.eventAtMs,
      `acknowledgement ${index} eventAtMs`,
    );
    const acknowledgementAtMs = finiteNonNegative(
      acknowledgement?.acknowledgementAtMs,
      `acknowledgement ${index} acknowledgementAtMs`,
    );
    if (acknowledgementAtMs < eventAtMs) {
      throw new RangeError("acknowledgement time precedes event time");
    }
    return acknowledgementAtMs - eventAtMs;
  });
  if (acknowledgementMs.length === 0) {
    return {
      acknowledgementMs: [],
      p50Ms: null,
      p95Ms: null,
      p99Ms: null,
    };
  }
  return {
    acknowledgementMs,
    p50Ms: percentile(acknowledgementMs, 0.5),
    p95Ms: percentile(acknowledgementMs, 0.95),
    p99Ms: percentile(acknowledgementMs, 0.99),
  };
}


function triggerSummary(sharedControl, acknowledgements) {
  if (sharedControl.acknowledgedCount !== acknowledgements.length) {
    throw new Error("acknowledgement count does not match records");
  }
  if (sharedControl.acknowledgedCount > sharedControl.dispatchedCount) {
    throw new Error("acknowledgement count exceeds dispatched count");
  }
  let pointerAcknowledgements = 0;
  let midiAcknowledgements = 0;
  for (const [index, acknowledgement] of acknowledgements.entries()) {
    nonNegativeInteger(
      acknowledgement?.sequence,
      `acknowledgement ${index} sequence`,
    );
    if (acknowledgement?.source === "pointer") {
      pointerAcknowledgements += 1;
    } else if (acknowledgement?.source === "midi") {
      midiAcknowledgements += 1;
    } else {
      throw new TypeError(`acknowledgement ${index} source is invalid`);
    }
  }
  return {
    dispatchedCount: sharedControl.dispatchedCount,
    acknowledgedCount: sharedControl.acknowledgedCount,
    missedAcknowledgements:
      sharedControl.dispatchedCount - sharedControl.acknowledgedCount,
    duplicateAcknowledgements: sharedControl.duplicateAcknowledgements,
    pointerAcknowledgements,
    midiAcknowledgements,
  };
}


export function createReport(session) {
  const sharedControl = sharedControlReport(session?.sharedControl);
  const acknowledgements = session?.triggerAcknowledgements;
  const estimates = acknowledgementEstimates(acknowledgements);
  const errors = session?.errors;
  if (!Array.isArray(errors) || errors.some((error) => typeof error !== "string")) {
    throw new TypeError("errors must be an array of strings");
  }

  return {
    reportVersion: 1,
    decisionStatus: "pending-threshold-approval",
    sessionId: requiredString(session?.sessionId, "sessionId"),
    startedAt: requiredString(session?.startedAt, "startedAt"),
    endedAt: requiredString(session?.endedAt, "endedAt"),
    environment: environmentReport(session?.environment),
    capabilities: capabilitiesReport(session?.capabilities),
    audioContext: audioContextReport(session?.audioContext),
    wasm: wasmReport(session?.wasm),
    sharedControl,
    midi: midiReport(session?.midi),
    lifecycle: lifecycleReport(session?.lifecycle),
    triggerSummary: triggerSummary(sharedControl, acknowledgements),
    browserEstimates: estimates,
    physicalMeasurement: null,
    errors: [...errors],
  };
}
