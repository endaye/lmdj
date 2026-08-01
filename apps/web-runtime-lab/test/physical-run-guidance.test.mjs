import assert from "node:assert/strict";
import test from "node:test";

import {
  BROWSER_RUN_TARGETS,
  evaluateBrowserRunGuidance,
} from "../src/physical-run-guidance.mjs";


function observation(overrides = {}) {
  return {
    startedAtMs: 1_000,
    nowMs: 1_000,
    dispatchedCount: 0,
    acknowledgedCount: 0,
    duplicateAcknowledgements: 0,
    droppedCount: 0,
    processorErrors: 0,
    audioState: "running",
    visibilityState: "visible",
    interrupted: false,
    oldestPendingAtMs: null,
    ...overrides,
  };
}


test("approved browser-run targets are exact and frozen", () => {
  assert.deepEqual(BROWSER_RUN_TARGETS, {
    triggerCount: 500,
    foregroundDurationMs: 600_000,
  });
  assert.equal(Object.isFrozen(BROWSER_RUN_TARGETS), true);
});


test("guidance stays not-started until audio has started", () => {
  assert.deepEqual(evaluateBrowserRunGuidance(observation({
    startedAtMs: null,
    nowMs: 99_000,
  })), {
    status: "not-started",
    elapsedMs: 0,
    remainingMs: 600_000,
    remainingTriggers: 500,
    reasons: ["audio-not-started"],
  });
});


test("guidance reports exact collection progress", () => {
  assert.deepEqual(evaluateBrowserRunGuidance(observation({
    nowMs: 301_000,
    dispatchedCount: 125,
    acknowledgedCount: 125,
  })), {
    status: "collecting",
    elapsedMs: 300_000,
    remainingMs: 300_000,
    remainingTriggers: 375,
    reasons: [],
  });
});


test("an acknowledgement still inside the grace window stays collecting", () => {
  const result = evaluateBrowserRunGuidance(observation({
    nowMs: 101_000,
    dispatchedCount: 125,
    acknowledgedCount: 124,
    oldestPendingAtMs: 100_500,
  }));

  assert.equal(result.status, "collecting");
  assert.deepEqual(result.reasons, []);
});


test("exact browser targets become ready without claiming physical pass", () => {
  const result = evaluateBrowserRunGuidance(observation({
    nowMs: 601_000,
    dispatchedCount: 500,
    acknowledgedCount: 500,
  }));

  assert.deepEqual(result, {
    status: "browser-target-ready",
    elapsedMs: 600_000,
    remainingMs: 0,
    remainingTriggers: 0,
    reasons: [],
  });
  assert.equal("passed" in result, false);
  assert.equal("physical" in result, false);
});


test("invalidating observations require a fresh run", () => {
  const cases = [
    [{ dispatchedCount: 501, acknowledgedCount: 501 }, "trigger-count-above-500"],
    [{ dispatchedCount: 500, acknowledgedCount: 499 }, "acknowledgement-loss"],
    [{ duplicateAcknowledgements: 1 }, "duplicate-acknowledgement"],
    [{ droppedCount: 1 }, "ring-full-drop"],
    [{ processorErrors: 1 }, "processor-error"],
    [{ audioState: "suspended" }, "audio-not-running"],
    [{ visibilityState: "hidden" }, "page-not-visible"],
    [{ interrupted: true }, "foreground-interrupted"],
  ];

  for (const [overrides, expectedReason] of cases) {
    const result = evaluateBrowserRunGuidance(observation(overrides));
    assert.equal(result.status, "restart-required", expectedReason);
    assert.equal(result.reasons.includes(expectedReason), true, expectedReason);
  }
});


test("invalid observation types are rejected", () => {
  assert.throws(() => evaluateBrowserRunGuidance(observation({
    nowMs: 999,
  })), /nowMs must not precede startedAtMs/);
  assert.throws(() => evaluateBrowserRunGuidance(observation({
    dispatchedCount: 1.5,
  })), /dispatchedCount/);
  assert.throws(() => evaluateBrowserRunGuidance(observation({
    interrupted: "false",
  })), /interrupted/);
  assert.throws(() => evaluateBrowserRunGuidance(observation({
    oldestPendingAtMs: -1,
  })), /oldestPendingAtMs/);
});
