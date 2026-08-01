const ELIGIBLE_ROUTES = new Set(["built-in", "wired"]);
const REQUIRED_LIFECYCLE_ACTIONS = Object.freeze([
  "background",
  "foreground",
  "lock",
  "unlock",
  "route-interruption",
]);


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
    requiresForeground: true,
  },
  {
    key: "macos-chrome-pointer-performance",
    kind: "performance",
    requiresForeground: true,
  },
  {
    key: "macos-chrome-midi-performance",
    kind: "performance",
    requiresMidiAcknowledgements: true,
  },
  {
    key: "ipados-safari-touch-performance",
    kind: "performance",
    requiresForeground: true,
  },
  {
    key: "ipados-safari-touch-lifecycle",
    kind: "lifecycle",
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


function percentile(values, proportion) {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.ceil(sorted.length * proportion) - 1];
}


function evaluatePhysical(physical) {
  if (!isObject(physical)) {
    return { failed: [], unverified: ["physical-evidence-missing"] };
  }
  if (
    !isCount(physical.triggerCount)
    || !isMeasurement(physical.p95Ms)
    || !isMeasurement(physical.p99Ms)
    || !isCount(physical.missedOnsets)
    || !isCount(physical.duplicateOnsets)
    || physical.p99Ms < physical.p95Ms
  ) {
    return { failed: [], unverified: ["physical-evidence-invalid"] };
  }

  const failed = [];
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
  return { failed, unverified: [] };
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


function rowResult(row, runsByKey) {
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
  if (!isObject(run) || !ELIGIBLE_ROUTES.has(run.routeCategory)) {
    return {
      key: row.key,
      status: "unverified",
      reasons: ["route-not-eligible"],
    };
  }

  const checks = row.kind === "lifecycle"
    ? [evaluateLifecycle(run.lifecycle)]
    : [evaluatePhysical(run.physical)];
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
  for (const run of evidence.runs) {
    const key = isObject(run) && typeof run.key === "string" ? run.key : null;
    if (key === null) {
      continue;
    }
    const matches = runsByKey.get(key) ?? [];
    matches.push(run);
    runsByKey.set(key, matches);
  }

  const requiredRows = REQUIRED_ROWS.map((row) => rowResult(row, runsByKey));
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
