import assert from "node:assert/strict";
import test from "node:test";

import {
  createReport,
  percentile,
  preflight,
} from "../src/probe-core.mjs";


function readyCapabilities() {
  return {
    secureContext: true,
    crossOriginIsolated: true,
    sharedArrayBuffer: true,
    atomics: true,
    audioContext: true,
    audioWorkletNode: true,
    webAssembly: true,
  };
}


function fixtureSession() {
  return {
    sessionId: "00000000-0000-4000-8000-000000000001",
    startedAt: "2026-08-01T00:00:00.000Z",
    endedAt: "2026-08-01T00:01:00.000Z",
    environment: {
      userAgent: "Runtime Lab Browser",
      platform: "Test Platform",
      language: "en-US",
      routeCategory: "built-in",
    },
    capabilities: readyCapabilities(),
    audioContext: {
      state: "running",
      sampleRate: 48000,
      baseLatency: 0.01,
      outputLatency: 0.02,
      observedQuantumSizes: [128],
    },
    wasm: {
      ready: true,
      calls: 42,
    },
    sharedControl: {
      dispatchedCount: 3,
      acknowledgedCount: 2,
      duplicateAcknowledgements: 0,
    },
    midi: {
      supported: true,
      permission: "granted",
      inputCount: 1,
      eventCount: 1,
      lastNote: 36,
      lastVelocity: 100,
      deviceName: "MIDI Device Name",
      manufacturer: "Private Manufacturer",
      id: "stable-device-id",
    },
    lifecycle: [
      { type: "audio-state", state: "running", atMs: 10 },
      { type: "visibility", state: "visible", atMs: 20 },
    ],
    triggerAcknowledgements: [
      {
        sequence: 1,
        source: "pointer",
        note: 36,
        velocity: 100,
        eventAtMs: 100,
        acknowledgementAtMs: 109,
        renderFrame: 4800,
        contextTime: 0.1,
        quantumSize: 128,
      },
      {
        sequence: 2,
        source: "midi",
        note: 38,
        velocity: 90,
        eventAtMs: 200,
        acknowledgementAtMs: 215,
        renderFrame: 9600,
        contextTime: 0.2,
        quantumSize: 128,
      },
    ],
    physicalMeasurement: {
      p95Ms: 1,
      deviceSerial: "must-not-leak",
    },
    errors: ["example diagnostic"],
  };
}


test("preflight requires every realtime primitive", () => {
  assert.deepEqual(preflight(readyCapabilities()), {
    ready: true,
    missing: [],
  });
});


test("preflight names all missing primitives in stable order", () => {
  assert.deepEqual(preflight({}), {
    ready: false,
    missing: [
      "secureContext",
      "crossOriginIsolated",
      "sharedArrayBuffer",
      "atomics",
      "audioContext",
      "audioWorkletNode",
      "webAssembly",
    ],
  });
});


test("percentile uses nearest-rank over finite non-negative values", () => {
  assert.equal(percentile([5, 1, 9, 3], 0.5), 3);
  assert.equal(percentile([5, 1, 9, 3], 0.95), 9);
  assert.throws(() => percentile([], 0.95), /non-empty/);
  assert.throws(() => percentile([1, Number.NaN], 0.95), /finite/);
  assert.throws(() => percentile([-1, 2], 0.95), /non-negative/);
  assert.throws(() => percentile([1], 0), /greater than zero/);
  assert.throws(() => percentile([1], 1.01), /at most one/);
});


test("report separates browser estimates from physical measurement", () => {
  const report = createReport(fixtureSession());

  assert.equal(report.reportVersion, 1);
  assert.equal(report.decisionStatus, "pending-threshold-approval");
  assert.deepEqual(report.triggerSummary, {
    dispatchedCount: 3,
    acknowledgedCount: 2,
    missedAcknowledgements: 1,
    duplicateAcknowledgements: 0,
    pointerAcknowledgements: 1,
    midiAcknowledgements: 1,
  });
  assert.deepEqual(report.browserEstimates, {
    acknowledgementMs: [9, 15],
    p50Ms: 9,
    p95Ms: 15,
    p99Ms: 15,
  });
  assert.equal(report.physicalMeasurement, null);
  assert.equal("pass" in report, false);
});


test("report whitelists MIDI and environment fields", () => {
  const report = createReport(fixtureSession());
  const serialized = JSON.stringify(report);

  assert.deepEqual(report.midi, {
    supported: true,
    permission: "granted",
    inputCount: 1,
    eventCount: 1,
    lastNote: 36,
    lastVelocity: 100,
  });
  assert.deepEqual(report.environment, {
    userAgent: "Runtime Lab Browser",
    platform: "Test Platform",
    language: "en-US",
    routeCategory: "built-in",
  });
  for (const forbidden of [
    "MIDI Device Name",
    "Private Manufacturer",
    "stable-device-id",
    "must-not-leak",
  ]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
});


test("report rejects inconsistent acknowledgement counts", () => {
  const session = fixtureSession();
  session.sharedControl.acknowledgedCount = 1;

  assert.throws(() => createReport(session), /acknowledgement count/);
});
