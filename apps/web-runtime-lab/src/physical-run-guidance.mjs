export const BROWSER_RUN_TARGETS = Object.freeze({
  triggerCount: 500,
  foregroundDurationMs: 600_000,
});

const ACKNOWLEDGEMENT_GRACE_MS = 1_000;
const ELIGIBLE_PHYSICAL_ROUTES = new Set(["built-in", "wired"]);


function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}


function nonNegativeNumber(value, label) {
  if (!Number.isFinite(value) || value < 0) {
    throw new TypeError(`${label} must be finite and non-negative`);
  }
  return value;
}


function nonNegativeInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError(`${label} must be a non-negative safe integer`);
  }
  return value;
}


export function isEligiblePhysicalRoute(routeCategory) {
  return ELIGIBLE_PHYSICAL_ROUTES.has(routeCategory);
}


export function canDispatchBrowserTrigger(dispatchedCount) {
  return nonNegativeInteger(dispatchedCount, "dispatchedCount")
    < BROWSER_RUN_TARGETS.triggerCount;
}


export function evaluateBrowserRunGuidance(observation) {
  if (!isObject(observation)) {
    throw new TypeError("observation must be an object");
  }
  const startedAtMs = observation.startedAtMs === null
    ? null
    : nonNegativeNumber(observation.startedAtMs, "startedAtMs");
  const nowMs = nonNegativeNumber(observation.nowMs, "nowMs");
  const dispatchedCount = nonNegativeInteger(
    observation.dispatchedCount,
    "dispatchedCount",
  );
  const acknowledgedCount = nonNegativeInteger(
    observation.acknowledgedCount,
    "acknowledgedCount",
  );
  const duplicateAcknowledgements = nonNegativeInteger(
    observation.duplicateAcknowledgements,
    "duplicateAcknowledgements",
  );
  const droppedCount = nonNegativeInteger(
    observation.droppedCount,
    "droppedCount",
  );
  const processorErrors = nonNegativeInteger(
    observation.processorErrors,
    "processorErrors",
  );
  const oldestPendingAtMs = observation.oldestPendingAtMs === null
    ? null
    : nonNegativeNumber(
      observation.oldestPendingAtMs,
      "oldestPendingAtMs",
    );
  if (typeof observation.audioState !== "string") {
    throw new TypeError("audioState must be a string");
  }
  if (typeof observation.visibilityState !== "string") {
    throw new TypeError("visibilityState must be a string");
  }
  if (typeof observation.interrupted !== "boolean") {
    throw new TypeError("interrupted must be boolean");
  }

  if (startedAtMs === null) {
    return {
      status: "not-started",
      elapsedMs: 0,
      remainingMs: BROWSER_RUN_TARGETS.foregroundDurationMs,
      remainingTriggers: BROWSER_RUN_TARGETS.triggerCount,
      reasons: ["audio-not-started"],
    };
  }
  if (nowMs < startedAtMs) {
    throw new RangeError("nowMs must not precede startedAtMs");
  }
  if (oldestPendingAtMs !== null && oldestPendingAtMs > nowMs) {
    throw new RangeError("oldestPendingAtMs must not exceed nowMs");
  }

  const elapsedMs = nowMs - startedAtMs;
  const remainingMs = Math.max(
    0,
    BROWSER_RUN_TARGETS.foregroundDurationMs - elapsedMs,
  );
  const remainingTriggers = Math.max(
    0,
    BROWSER_RUN_TARGETS.triggerCount - dispatchedCount,
  );
  const reasons = [];
  if (dispatchedCount > BROWSER_RUN_TARGETS.triggerCount) {
    reasons.push("trigger-count-above-500");
  }
  const acknowledgementPending = acknowledgedCount < dispatchedCount
    && oldestPendingAtMs !== null
    && nowMs - oldestPendingAtMs <= ACKNOWLEDGEMENT_GRACE_MS;
  if (acknowledgedCount < dispatchedCount && !acknowledgementPending) {
    reasons.push("acknowledgement-loss");
  } else if (acknowledgedCount > dispatchedCount) {
    reasons.push("acknowledgement-count-above-dispatch");
  }
  if (duplicateAcknowledgements > 0) {
    reasons.push("duplicate-acknowledgement");
  }
  if (droppedCount > 0) {
    reasons.push("ring-full-drop");
  }
  if (processorErrors > 0) {
    reasons.push("processor-error");
  }
  if (observation.audioState !== "running") {
    reasons.push("audio-not-running");
  }
  if (observation.visibilityState !== "visible") {
    reasons.push("page-not-visible");
  }
  if (observation.interrupted) {
    reasons.push("foreground-interrupted");
  }

  if (reasons.length > 0) {
    return {
      status: "restart-required",
      elapsedMs,
      remainingMs,
      remainingTriggers,
      reasons,
    };
  }
  const ready = dispatchedCount === BROWSER_RUN_TARGETS.triggerCount
    && acknowledgedCount === BROWSER_RUN_TARGETS.triggerCount
    && remainingMs === 0;
  return {
    status: ready ? "browser-target-ready" : "collecting",
    elapsedMs,
    remainingMs,
    remainingTriggers,
    reasons: [],
  };
}
