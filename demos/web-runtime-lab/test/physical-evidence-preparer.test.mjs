import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import { evaluatePhysicalMatrix } from "../src/physical-gate.mjs";
import { preparePhysicalEvidence } from "../src/physical-evidence-preparer.mjs";


const OPTIONS = Object.freeze({
  osVersion: "macOS 26.5.2 (25F84)",
  browserVersion: "Safari 26.5.2 (21624.2.5.11.8)",
});


function reportFixture(source = "pointer", count = 500) {
  const records = Array.from({ length: count }, (_, index) => ({
    sequence: index + 1,
    source,
    note: 36,
    velocity: 100,
    eventAtMs: index * 10,
    acknowledgementAtMs: index * 10 + 2,
    acknowledgementMs: 2,
    renderFrame: index * 128,
    contextTime: index * 128 / 48_000,
    quantumSize: 128,
    privateRecordField: "must-not-copy",
  }));
  const pointerCount = source === "pointer" ? count : 0;
  const touchCount = source === "touch" ? count : 0;
  const midiCount = source === "midi" ? count : 0;
  const triggerDispatches = records.map((record) => ({
    sequence: record.sequence,
    source: record.source,
    note: record.note,
    velocity: record.velocity,
    eventAtMs: record.eventAtMs,
  }));
  return {
    reportVersion: 2,
    decisionStatus: "threshold-approved",
    sessionId: "00000000-0000-4000-8000-000000000010",
    startedAt: "2026-08-01T12:00:00.000Z",
    endedAt: "2026-08-01T12:10:00.000Z",
    environment: {
      userAgent: "private-user-agent",
      platform: "private-raw-platform",
      language: "private-language",
      routeCategory: "built-in",
    },
    capabilities: {
      secureContext: true,
      crossOriginIsolated: true,
      sharedArrayBuffer: true,
      atomics: true,
      audioContext: true,
      audioWorkletNode: true,
      webAssembly: true,
    },
    audioContext: {
      state: "running",
      sampleRate: 48_000,
      baseLatency: 0.003,
      outputLatency: 0.016,
      observedQuantumSizes: [128],
      lastOutputTimestamp: {
        contextTime: 600,
        performanceTime: 600_000,
      },
    },
    wasm: { ready: true, calls: 225_000 },
    sharedControl: {
      dispatchedCount: count,
      acknowledgedCount: count,
      duplicateAcknowledgements: 0,
      droppedCount: 0,
    },
    midi: {
      supported: source === "midi",
      permission: source === "midi" ? "granted" : "not-requested",
      inputCount: source === "midi" ? 1 : 0,
      eventCount: midiCount,
      lastNote: source === "midi" ? 36 : null,
      lastVelocity: source === "midi" ? 100 : null,
      name: "must-not-copy-midi-name",
      manufacturer: "must-not-copy-midi-manufacturer",
      id: "must-not-copy-midi-id",
    },
    lifecycle: [
      { type: "pageshow", state: "visible", atMs: 0 },
      { type: "audio-state", state: "running", atMs: 10 },
    ],
    triggerDispatches,
    triggerSummary: {
      dispatchedCount: count,
      acknowledgedCount: count,
      missedAcknowledgements: 0,
      duplicateAcknowledgements: 0,
      pointerAcknowledgements: pointerCount,
      touchAcknowledgements: touchCount,
      midiAcknowledgements: midiCount,
    },
    browserEstimates: {
      records,
      acknowledgementMs: records.map(() => 2),
      p50Ms: 2,
      p95Ms: 2,
      p99Ms: 2,
    },
    physicalMeasurement: null,
    errors: [],
    arbitraryPrivateField: "must-not-copy-private-field",
  };
}


test("preparer maps one performance report into a privacy-bounded draft", () => {
  const draft = preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    reportFixture(),
    OPTIONS,
  );
  const run = draft.runs[0];

  assert.equal(draft.evidenceVersion, 1);
  assert.deepEqual(run.environment, {
    platform: "macos",
    browser: "safari",
    osVersion: OPTIONS.osVersion,
    browserVersion: OPTIONS.browserVersion,
    deviceClass: "mac",
    inputSource: "pointer",
    routeCategory: "built-in",
    sampleRate: 48_000,
  });
  assert.deepEqual(run.runtime, {
    audioContextStateHistory: [{ state: "running", atMs: 10 }],
    baseLatency: 0.003,
    outputLatency: 0.016,
    observedQuantumSizes: [128],
    processorCallbackCount: 225_000,
  });
  assert.equal(run.triggerRecords.length, 500);
  assert.deepEqual(run.triggerRecords[0], {
    sequence: 1,
    source: "pointer",
    eventAtMs: 0,
    acknowledgementAtMs: 2,
    quantumSize: 128,
  });
  assert.deepEqual(run.physical, {
    method: null,
    captureRateHz: null,
    calibrationOffsetMs: null,
    triggerCount: 500,
    p50Ms: null,
    p95Ms: null,
    p99Ms: null,
    missedOnsets: null,
    duplicateOnsets: null,
  });
  assert.deepEqual(run.foreground, {
    durationMs: null,
    underruns: null,
    processorErrors: 0,
    lostAcknowledgements: 0,
    duplicateAcknowledgements: 0,
  });

  const serialized = JSON.stringify(draft);
  for (const forbidden of [
    "private-user-agent",
    "private-raw-platform",
    "private-language",
    "must-not-copy-midi-name",
    "must-not-copy-midi-manufacturer",
    "must-not-copy-midi-id",
    "must-not-copy-private-field",
    "must-not-copy",
  ]) {
    assert.equal(serialized.includes(forbidden), false, forbidden);
  }
  assert.equal(evaluatePhysicalMatrix(draft).status, "unverified");
});


test("preparer retains a missing acknowledgement as measured failure", () => {
  const report = reportFixture();
  report.browserEstimates.records.pop();
  report.browserEstimates.acknowledgementMs.pop();
  report.sharedControl.acknowledgedCount = 499;
  report.triggerSummary.acknowledgedCount = 499;
  report.triggerSummary.missedAcknowledgements = 1;
  report.triggerSummary.pointerAcknowledgements = 499;
  const draft = preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    report,
    OPTIONS,
  );

  assert.equal(draft.runs[0].triggerRecords.length, 500);
  assert.deepEqual(draft.runs[0].triggerRecords[499], {
    sequence: 500,
    source: "pointer",
    eventAtMs: 4990,
    acknowledgementAtMs: null,
    quantumSize: null,
  });
  assert.equal(draft.runs[0].foreground.lostAcknowledgements, 1);
  assert.equal(evaluatePhysicalMatrix(draft).status, "failed");
});


test("preparer preserves processorerror as a structured gate failure", () => {
  const report = reportFixture();
  report.errors.push("AudioWorklet processorerror");
  const draft = preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    report,
    OPTIONS,
  );

  assert.equal(draft.runs[0].foreground.processorErrors, 1);
  assert.equal(evaluatePhysicalMatrix(draft).status, "failed");
});


test("preparer preserves iPad touch identity without treating it as pointer", () => {
  const draft = preparePhysicalEvidence(
    "ipados-safari-touch-performance",
    reportFixture("touch"),
    { osVersion: "iPadOS exact", browserVersion: "Safari exact" },
  );

  assert.equal(draft.runs[0].environment.inputSource, "touch");
  assert.equal(draft.runs[0].triggerRecords[0].source, "touch");
  assert.equal(evaluatePhysicalMatrix(draft).status, "unverified");
});


test("lifecycle preparation never fabricates recovery observations", () => {
  const draft = preparePhysicalEvidence(
    "ipados-safari-touch-lifecycle",
    reportFixture("touch", 1),
    { osVersion: "iPadOS exact", browserVersion: "Safari exact" },
  );

  assert.equal("triggerRecords" in draft.runs[0], false);
  assert.deepEqual(draft.runs[0].lifecycle, {
    actions: [],
    recoverySamplesMs: [],
    maxExplicitActivations: null,
    postRecoveryMissedOnsets: null,
    postRecoveryDuplicateOnsets: null,
  });
  assert.equal(evaluatePhysicalMatrix(draft).status, "unverified");
});


test("preparer rejects stale reports and non-null physical fields", () => {
  const stale = reportFixture();
  stale.reportVersion = 1;
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    stale,
    OPTIONS,
  ), /reportVersion 2/);

  const measured = reportFixture();
  measured.physicalMeasurement = { p95Ms: 1 };
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    measured,
    OPTIONS,
  ), /physicalMeasurement must be null/);
});


test("preparer rejects ineligible routes and incomplete runtime evidence", () => {
  const bluetooth = reportFixture();
  bluetooth.environment.routeCategory = "bluetooth";
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    bluetooth,
    OPTIONS,
  ), /built-in or wired/);

  const noRunningState = reportFixture();
  noRunningState.lifecycle = [{ type: "visibility", state: "visible", atMs: 0 }];
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    noRunningState,
    OPTIONS,
  ), /running AudioContext/);
});


test("preparer rejects wrong or incomplete performance input", () => {
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    reportFixture("pointer", 499),
    OPTIONS,
  ), /exactly 500/);
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    reportFixture("midi"),
    OPTIONS,
  ), /source pointer/);

  const midiDenied = reportFixture("midi");
  midiDenied.midi.permission = "denied-or-error";
  assert.throws(() => preparePhysicalEvidence(
    "macos-chrome-midi-performance",
    midiDenied,
    OPTIONS,
  ), /granted physical MIDI/);
});


test("preparer requires a known row and explicit exact versions", () => {
  assert.throws(() => preparePhysicalEvidence(
    "unknown-row",
    reportFixture(),
    OPTIONS,
  ), /required row/);
  assert.throws(() => preparePhysicalEvidence(
    "macos-safari-pointer-performance",
    reportFixture(),
    { osVersion: "", browserVersion: "Safari exact" },
  ), /osVersion/);
});


test("CLI emits a deterministic draft and usage errors", () => {
  const directory = mkdtempSync(join(tmpdir(), "lmdj-web-prepare-"));
  try {
    const reportPath = join(directory, "report.json");
    writeFileSync(reportPath, JSON.stringify(reportFixture()));
    const prepared = spawnSync(
      process.execPath,
      [
        "src/prepare-physical-evidence.mjs",
        "macos-safari-pointer-performance",
        reportPath,
        "--os-version",
        OPTIONS.osVersion,
        "--browser-version",
        OPTIONS.browserVersion,
      ],
      { cwd: new URL("..", import.meta.url), encoding: "utf8" },
    );
    assert.equal(prepared.status, 0, prepared.stderr);
    assert.equal(JSON.parse(prepared.stdout).runs[0].triggerRecords.length, 500);

    const usage = spawnSync(
      process.execPath,
      ["src/prepare-physical-evidence.mjs"],
      { cwd: new URL("..", import.meta.url), encoding: "utf8" },
    );
    assert.equal(usage.status, 64);
    assert.match(JSON.parse(usage.stderr).error, /usage/);
  } finally {
    rmSync(directory, { recursive: true });
  }
});
