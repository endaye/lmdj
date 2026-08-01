const ELIGIBLE_ROUTES = new Set(["built-in", "wired"]);
const REQUIRED_LIFECYCLE_ACTIONS = Object.freeze([
  "background",
  "foreground",
  "lock",
  "unlock",
  "route-interruption",
]);
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;


function deepFreeze(value) {
  Object.freeze(value);
  for (const child of Object.values(value)) {
    if (child !== null && typeof child === "object" && !Object.isFrozen(child)) {
      deepFreeze(child);
    }
  }
  return value;
}


export const APPROVED_GATE = deepFreeze({
  touchToSound: {
    p95Ms: 50,
    p99Ms: 80,
    triggerCount: 500,
    missedOnsets: 0,
    duplicateOnsets: 0,
  },
  foreground: {
    durationMs: 600_000,
    underruns: 0,
    processorErrors: 0,
    lostAcknowledgements: 0,
    duplicateAcknowledgements: 0,
  },
  lifecycle: {
    p95ActivationToRunningMs: 500,
    maxExplicitActivations: 1,
    postRecoveryMissedOnsets: 0,
    postRecoveryDuplicateOnsets: 0,
  },
});


export const REQUIRED_ROWS = deepFreeze([
  {
    key: "macos-safari-pointer-performance",
    kind: "performance",
    platform: "macos",
    browser: "safari",
    deviceClass: "mac",
    inputSource: "pointer",
    requiresForeground: true,
  },
  {
    key: "macos-chrome-pointer-performance",
    kind: "performance",
    platform: "macos",
    browser: "chrome",
    deviceClass: "mac",
    inputSource: "pointer",
    requiresForeground: true,
  },
  {
    key: "macos-chrome-midi-performance",
    kind: "performance",
    platform: "macos",
    browser: "chrome",
    deviceClass: "mac",
    inputSource: "midi",
    requiresMidiAcknowledgements: true,
  },
  {
    key: "ipados-safari-touch-performance",
    kind: "performance",
    platform: "ipados",
    browser: "safari",
    deviceClass: "ipad",
    inputSource: "touch",
    requiresForeground: true,
  },
  {
    key: "ipados-safari-touch-lifecycle",
    kind: "lifecycle",
    platform: "ipados",
    browser: "safari",
    deviceClass: "ipad",
    inputSource: "touch",
  },
]);


function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}


function isCount(value) {
  return Number.isInteger(value) && value >= 0;
}


function isMeasurement(value) {
  return Number.isFinite(value) && value >= 0;
}


function isFiniteNumber(value) {
  return Number.isFinite(value);
}


function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}


function percentile(values, proportion) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.ceil(sorted.length * proportion) - 1];
}


function evaluateRunEnvelope(run, row, duplicateSessionIds) {
  const unverified = [];
  if (!isNonEmptyString(run.sessionId) || !UUID_V4.test(run.sessionId)) {
    unverified.push("session-id-invalid");
  } else if (duplicateSessionIds.has(run.sessionId)) {
    unverified.push("duplicate-session-id");
  }

  if (
    !isNonEmptyString(run.recordedAt)
    || !run.recordedAt.endsWith("Z")
    || !Number.isFinite(Date.parse(run.recordedAt))
  ) {
    unverified.push("recorded-at-invalid");
  }

  const environment = run.environment;
  if (!isObject(environment)) {
    unverified.push("environment-evidence-missing");
  } else if (
    !isNonEmptyString(environment.osVersion)
    || !isNonEmptyString(environment.browserVersion)
    || !isNonEmptyString(environment.routeCategory)
    || !isMeasurement(environment.sampleRate)
    || environment.sampleRate === 0
  ) {
    unverified.push("environment-evidence-invalid");
  } else {
    if (environment.platform !== row.platform) {
      unverified.push("platform-mismatch");
    }
    if (environment.browser !== row.browser) {
      unverified.push("browser-mismatch");
    }
    if (environment.deviceClass !== row.deviceClass) {
      unverified.push("device-class-mismatch");
    }
    if (environment.inputSource !== row.inputSource) {
      unverified.push("input-source-mismatch");
    }
    if (!ELIGIBLE_ROUTES.has(environment.routeCategory)) {
      unverified.push("route-not-eligible");
    }
  }

  const runtime = run.runtime;
  if (!isObject(runtime)) {
    unverified.push("runtime-evidence-missing");
  } else {
    const states = runtime.audioContextStateHistory;
    const quantumSizes = runtime.observedQuantumSizes;
    const stateHistoryValid = Array.isArray(states)
      && states.length > 0
      && states.every((entry) => (
        isObject(entry)
        && isNonEmptyString(entry.state)
        && isMeasurement(entry.atMs)
      ))
      && states.some((entry) => entry.state === "running");
    const quantumSizesValid = Array.isArray(quantumSizes)
      && quantumSizes.length > 0
      && quantumSizes.every((size) => Number.isInteger(size) && size > 0)
      && new Set(quantumSizes).size === quantumSizes.length;
    const nullableLatency = (value) => value === null || isMeasurement(value);
    if (
      !stateHistoryValid
      || !nullableLatency(runtime.baseLatency)
      || !nullableLatency(runtime.outputLatency)
      || !quantumSizesValid
      || !Number.isInteger(runtime.processorCallbackCount)
      || runtime.processorCallbackCount <= 0
    ) {
      unverified.push("runtime-evidence-invalid");
    }
  }

  if (!Array.isArray(run.errors) || run.errors.some(
    (error) => typeof error !== "string",
  )) {
    unverified.push("errors-evidence-missing");
  } else if (run.errors.length > 0) {
    unverified.push("run-errors-present");
  }

  if (
    !Array.isArray(run.unsupportedCapabilities)
    || run.unsupportedCapabilities.some((capability) => (
      typeof capability !== "string"
    ))
  ) {
    unverified.push("unsupported-capabilities-evidence-missing");
  } else if (run.unsupportedCapabilities.length > 0) {
    unverified.push("unsupported-capabilities-present");
  }

  return { failed: [], unverified };
}


function evaluateTriggerRecords(run, row) {
  const records = run.triggerRecords;
  if (!Array.isArray(records)) {
    return { failed: [], unverified: ["trigger-records-missing"] };
  }

  const unverified = [];
  if (records.length !== APPROVED_GATE.touchToSound.triggerCount) {
    unverified.push("trigger-record-count-not-500");
  }

  const validSequences = [];
  let recordInvalid = false;
  let sourceMismatch = false;
  let quantumUnobserved = false;
  const observedQuantumSizes = new Set(
    Array.isArray(run.runtime?.observedQuantumSizes)
      ? run.runtime.observedQuantumSizes
      : [],
  );
  for (const record of records) {
    if (
      !isObject(record)
      || !Number.isInteger(record.sequence)
      || record.sequence <= 0
      || !isMeasurement(record.eventAtMs)
      || !isMeasurement(record.acknowledgementAtMs)
      || record.acknowledgementAtMs < record.eventAtMs
      || !Number.isInteger(record.quantumSize)
      || record.quantumSize <= 0
    ) {
      recordInvalid = true;
      continue;
    }
    validSequences.push(record.sequence);
    if (record.source !== row.inputSource) {
      sourceMismatch = true;
    }
    if (
      observedQuantumSizes.size > 0
      && !observedQuantumSizes.has(record.quantumSize)
    ) {
      quantumUnobserved = true;
    }
  }
  if (recordInvalid) {
    unverified.push("trigger-record-invalid");
  }
  if (new Set(validSequences).size !== validSequences.length) {
    unverified.push("trigger-sequence-duplicate");
  }
  if (sourceMismatch) {
    unverified.push("trigger-source-mismatch");
  }
  if (quantumUnobserved) {
    unverified.push("trigger-quantum-unobserved");
  }
  if (
    isObject(run.physical)
    && isCount(run.physical.triggerCount)
    && run.physical.triggerCount !== records.length
  ) {
    unverified.push("physical-trigger-count-mismatch");
  }
  return { failed: [], unverified };
}


function evaluatePhysical(physical) {
  if (!isObject(physical)) {
    return { failed: [], unverified: ["physical-evidence-missing"] };
  }
  const failed = [];
  const unverified = [];
  if (
    !isCount(physical.triggerCount)
    || !isMeasurement(physical.p95Ms)
    || !isMeasurement(physical.p99Ms)
    || !isCount(physical.missedOnsets)
    || !isCount(physical.duplicateOnsets)
    || physical.p99Ms < physical.p95Ms
  ) {
    unverified.push("physical-evidence-invalid");
  } else {
    if (physical.triggerCount < APPROVED_GATE.touchToSound.triggerCount) {
      failed.push("trigger-count-below-500");
    }
    if (physical.p95Ms > APPROVED_GATE.touchToSound.p95Ms) {
      failed.push("p95-above-50-ms");
    }
    if (physical.p99Ms > APPROVED_GATE.touchToSound.p99Ms) {
      failed.push("p99-above-80-ms");
    }
    if (physical.missedOnsets > APPROVED_GATE.touchToSound.missedOnsets) {
      failed.push("missed-onset");
    }
    if (physical.duplicateOnsets > APPROVED_GATE.touchToSound.duplicateOnsets) {
      failed.push("duplicate-onset");
    }
  }

  const methodFields = [
    physical.method,
    physical.captureRateHz,
    physical.calibrationOffsetMs,
    physical.p50Ms,
  ];
  if (methodFields.some((value) => value === undefined)) {
    unverified.push("physical-method-missing");
  } else if (
    !["high-speed-video", "wired-loopback"].includes(physical.method)
    || !isMeasurement(physical.captureRateHz)
    || physical.captureRateHz === 0
    || !isFiniteNumber(physical.calibrationOffsetMs)
    || !isMeasurement(physical.p50Ms)
    || (isMeasurement(physical.p95Ms) && physical.p50Ms > physical.p95Ms)
  ) {
    unverified.push("physical-method-invalid");
  } else if (
    physical.method === "high-speed-video"
    && physical.captureRateHz < 240
  ) {
    unverified.push("physical-video-rate-below-240-hz");
  }
  return { failed, unverified };
}


function evaluateForeground(foreground) {
  if (!isObject(foreground)) {
    return { failed: [], unverified: ["foreground-evidence-missing"] };
  }
  if (
    !isMeasurement(foreground.durationMs)
    || !isCount(foreground.underruns)
    || !isCount(foreground.processorErrors)
    || !isCount(foreground.lostAcknowledgements)
    || !isCount(foreground.duplicateAcknowledgements)
  ) {
    return { failed: [], unverified: ["foreground-evidence-invalid"] };
  }

  const failed = [];
  if (foreground.durationMs < APPROVED_GATE.foreground.durationMs) {
    failed.push("foreground-duration-below-600000-ms");
  }
  if (foreground.underruns > APPROVED_GATE.foreground.underruns) {
    failed.push("audio-underrun");
  }
  if (foreground.processorErrors > APPROVED_GATE.foreground.processorErrors) {
    failed.push("processor-error");
  }
  if (
    foreground.lostAcknowledgements
    > APPROVED_GATE.foreground.lostAcknowledgements
  ) {
    failed.push("acknowledgement-loss");
  }
  if (
    foreground.duplicateAcknowledgements
    > APPROVED_GATE.foreground.duplicateAcknowledgements
  ) {
    failed.push("duplicate-acknowledgement");
  }
  return { failed, unverified: [] };
}


function evaluateMidiAcknowledgements(acknowledgements) {
  if (!isObject(acknowledgements)) {
    return {
      failed: [],
      unverified: ["acknowledgement-evidence-missing"],
    };
  }
  if (
    !isCount(acknowledgements.triggerCount)
    || !isCount(acknowledgements.acknowledgedCount)
    || !isCount(acknowledgements.lostAcknowledgements)
    || !isCount(acknowledgements.duplicateAcknowledgements)
  ) {
    return {
      failed: [],
      unverified: ["acknowledgement-evidence-invalid"],
    };
  }

  const failed = [];
  if (acknowledgements.triggerCount < APPROVED_GATE.touchToSound.triggerCount) {
    failed.push("midi-trigger-count-below-500");
  }
  if (acknowledgements.acknowledgedCount !== acknowledgements.triggerCount) {
    failed.push("acknowledgement-parity-mismatch");
  }
  if (acknowledgements.lostAcknowledgements > 0) {
    failed.push("acknowledgement-loss");
  }
  if (acknowledgements.duplicateAcknowledgements > 0) {
    failed.push("duplicate-acknowledgement");
  }
  return { failed, unverified: [] };
}


function evaluateLifecycle(lifecycle) {
  if (!isObject(lifecycle)) {
    return { failed: [], unverified: ["lifecycle-evidence-missing"] };
  }
  if (
    !Array.isArray(lifecycle.actions)
    || lifecycle.actions.some((action) => typeof action !== "string")
    || new Set(lifecycle.actions).size !== lifecycle.actions.length
    || !Array.isArray(lifecycle.recoverySamplesMs)
    || lifecycle.recoverySamplesMs.length === 0
    || lifecycle.recoverySamplesMs.some((value) => !isMeasurement(value))
    || !isCount(lifecycle.maxExplicitActivations)
    || !isCount(lifecycle.postRecoveryMissedOnsets)
    || !isCount(lifecycle.postRecoveryDuplicateOnsets)
  ) {
    return { failed: [], unverified: ["lifecycle-evidence-invalid"] };
  }

  const unverified = [];
  const actions = new Set(lifecycle.actions);
  for (const action of REQUIRED_LIFECYCLE_ACTIONS) {
    if (!actions.has(action)) {
      unverified.push(`lifecycle-action-missing:${action}`);
    }
  }

  const failed = [];
  if (
    percentile(lifecycle.recoverySamplesMs, 0.95)
    > APPROVED_GATE.lifecycle.p95ActivationToRunningMs
  ) {
    failed.push("activation-p95-above-500-ms");
  }
  if (
    lifecycle.maxExplicitActivations
    > APPROVED_GATE.lifecycle.maxExplicitActivations
  ) {
    failed.push("explicit-activation-count-above-1");
  }
  if (
    lifecycle.postRecoveryMissedOnsets
    > APPROVED_GATE.lifecycle.postRecoveryMissedOnsets
  ) {
    failed.push("post-recovery-missed-onset");
  }
  if (
    lifecycle.postRecoveryDuplicateOnsets
    > APPROVED_GATE.lifecycle.postRecoveryDuplicateOnsets
  ) {
    failed.push("post-recovery-duplicate-onset");
  }
  return { failed, unverified };
}


function rowResult(row, runsByKey, duplicateSessionIds) {
  const matches = runsByKey.get(row.key) ?? [];
  if (matches.length === 0) {
    return {
      key: row.key,
      status: "unverified",
      reasons: ["physical-run-missing"],
    };
  }
  if (matches.length > 1) {
    return {
      key: row.key,
      status: "unverified",
      reasons: ["duplicate-run-key"],
    };
  }

  const run = matches[0];
  if (!isObject(run)) {
    return {
      key: row.key,
      status: "unverified",
      reasons: ["physical-run-invalid"],
    };
  }

  const checks = [evaluateRunEnvelope(run, row, duplicateSessionIds)];
  if (row.kind === "lifecycle") {
    checks.push(evaluateLifecycle(run.lifecycle));
  } else {
    checks.push(evaluateTriggerRecords(run, row));
    checks.push(evaluatePhysical(run.physical));
  }
  if (row.requiresForeground) {
    checks.push(evaluateForeground(run.foreground));
  }
  if (row.requiresMidiAcknowledgements) {
    checks.push(evaluateMidiAcknowledgements(run.acknowledgements));
  }

  const failed = checks.flatMap((check) => check.failed);
  const unverified = checks.flatMap((check) => check.unverified);
  return {
    key: row.key,
    status: failed.length > 0
      ? "failed"
      : unverified.length > 0
        ? "unverified"
        : "passed",
    reasons: [...failed, ...unverified],
  };
}


function unverifiedEvaluation(reason) {
  const requiredRows = REQUIRED_ROWS.map(({ key }) => ({
    key,
    status: "unverified",
    reasons: [reason],
  }));
  return {
    evidenceVersion: 1,
    status: "unverified",
    reasons: [reason],
    thresholds: APPROVED_GATE,
    requiredRows,
    missingRows: REQUIRED_ROWS.map(({ key }) => key),
    failedRows: [],
  };
}


export function evaluatePhysicalMatrix(evidence) {
  if (!isObject(evidence) || evidence.evidenceVersion !== 1) {
    return unverifiedEvaluation("evidence-version-unsupported");
  }
  if (!Array.isArray(evidence.runs)) {
    return unverifiedEvaluation("runs-invalid");
  }

  const runsByKey = new Map();
  const sessionIdCounts = new Map();
  for (const run of evidence.runs) {
    const key = isObject(run) && typeof run.key === "string" ? run.key : null;
    if (key === null) {
      continue;
    }
    const matches = runsByKey.get(key) ?? [];
    matches.push(run);
    runsByKey.set(key, matches);
    if (isNonEmptyString(run.sessionId) && UUID_V4.test(run.sessionId)) {
      sessionIdCounts.set(
        run.sessionId,
        (sessionIdCounts.get(run.sessionId) ?? 0) + 1,
      );
    }
  }

  const duplicateSessionIds = new Set(
    [...sessionIdCounts.entries()]
      .filter(([, count]) => count > 1)
      .map(([sessionId]) => sessionId),
  );

  const requiredRows = REQUIRED_ROWS.map((row) => (
    rowResult(row, runsByKey, duplicateSessionIds)
  ));
  const failedRows = requiredRows
    .filter(({ status }) => status === "failed")
    .map(({ key }) => key);
  const missingRows = requiredRows
    .filter(({ status }) => status === "unverified")
    .map(({ key }) => key);
  return {
    evidenceVersion: 1,
    status: failedRows.length > 0
      ? "failed"
      : missingRows.length > 0
        ? "unverified"
        : "passed",
    reasons: [],
    thresholds: APPROVED_GATE,
    requiredRows,
    missingRows,
    failedRows,
  };
}
