import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";

import {
  APPROVED_GATE,
  REQUIRED_ROWS,
  evaluatePhysicalMatrix,
} from "../src/physical-gate.mjs";


function performanceRun(key) {
  return {
    key,
    routeCategory: "built-in",
    physical: {
      triggerCount: 500,
      p95Ms: 50,
      p99Ms: 80,
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
  };
}


function midiRun() {
  return {
    ...performanceRun("macos-chrome-midi-performance"),
    acknowledgements: {
      triggerCount: 500,
      acknowledgedCount: 500,
      lostAcknowledgements: 0,
      duplicateAcknowledgements: 0,
    },
  };
}


function lifecycleRun() {
  return {
    key: "ipados-safari-touch-lifecycle",
    routeCategory: "wired",
    lifecycle: {
      actions: [
        "background",
        "foreground",
        "lock",
        "unlock",
        "route-interruption",
      ],
      recoverySamplesMs: [250, 500],
      maxExplicitActivations: 1,
      postRecoveryMissedOnsets: 0,
      postRecoveryDuplicateOnsets: 0,
    },
  };
}


function passingEvidence() {
  return {
    evidenceVersion: 1,
    runs: [
      performanceRun("macos-safari-pointer-performance"),
      performanceRun("macos-chrome-pointer-performance"),
      midiRun(),
      performanceRun("ipados-safari-touch-performance"),
      lifecycleRun(),
    ],
  };
}


test("approved thresholds and required rows are exact and frozen", () => {
  assert.equal(Object.isFrozen(APPROVED_GATE), true);
  assert.deepEqual(APPROVED_GATE, {
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
  assert.deepEqual(REQUIRED_ROWS.map((row) => row.key), [
    "macos-safari-pointer-performance",
    "macos-chrome-pointer-performance",
    "macos-chrome-midi-performance",
    "ipados-safari-touch-performance",
    "ipados-safari-touch-lifecycle",
  ]);
});


test("all five eligible physical rows pass at the exact boundaries", () => {
  const evaluation = evaluatePhysicalMatrix(passingEvidence());

  assert.equal(evaluation.status, "passed");
  assert.deepEqual(evaluation.missingRows, []);
  assert.deepEqual(evaluation.failedRows, []);
  assert.deepEqual(
    evaluation.requiredRows.map(({ key, status, reasons }) => ({
      key,
      status,
      reasons,
    })),
    REQUIRED_ROWS.map(({ key }) => ({ key, status: "passed", reasons: [] })),
  );
});


test("missing physical rows remain unverified", () => {
  const evaluation = evaluatePhysicalMatrix({
    evidenceVersion: 1,
    browserEstimates: { p95Ms: 1, p99Ms: 2 },
    runs: [],
  });

  assert.equal(evaluation.status, "unverified");
  assert.deepEqual(evaluation.missingRows, REQUIRED_ROWS.map(({ key }) => key));
  assert.equal(evaluation.failedRows.length, 0);
  assert.deepEqual(evaluation.requiredRows[0].reasons, ["physical-run-missing"]);
});


test("one required threshold failure outranks other missing evidence", () => {
  const failedRun = performanceRun("macos-safari-pointer-performance");
  failedRun.physical.p95Ms = 50.01;
  const evaluation = evaluatePhysicalMatrix({
    evidenceVersion: 1,
    runs: [failedRun],
  });

  assert.equal(evaluation.status, "failed");
  assert.deepEqual(evaluation.failedRows, [
    "macos-safari-pointer-performance",
  ]);
  assert.deepEqual(evaluation.requiredRows[0].reasons, ["p95-above-50-ms"]);
  assert.equal(evaluation.missingRows.length, 4);
});


test("Bluetooth evidence never satisfies a required row", () => {
  const evidence = passingEvidence();
  evidence.runs[0].routeCategory = "bluetooth";
  const evaluation = evaluatePhysicalMatrix(evidence);

  assert.equal(evaluation.status, "unverified");
  assert.deepEqual(evaluation.requiredRows[0].reasons, ["route-not-eligible"]);
  assert.deepEqual(evaluation.missingRows, [
    "macos-safari-pointer-performance",
  ]);
});


test("duplicated or unsupported evidence remains unverified", () => {
  const duplicate = passingEvidence();
  duplicate.runs.push(performanceRun("macos-safari-pointer-performance"));
  const duplicateEvaluation = evaluatePhysicalMatrix(duplicate);
  assert.equal(duplicateEvaluation.status, "unverified");
  assert.deepEqual(duplicateEvaluation.requiredRows[0].reasons, [
    "duplicate-run-key",
  ]);

  const unsupported = passingEvidence();
  unsupported.evidenceVersion = 2;
  const unsupportedEvaluation = evaluatePhysicalMatrix(unsupported);
  assert.equal(unsupportedEvaluation.status, "unverified");
  assert.deepEqual(unsupportedEvaluation.reasons, [
    "evidence-version-unsupported",
  ]);
});


test("missing foreground, MIDI parity, and lifecycle actions are explicit", () => {
  const evidence = passingEvidence();
  delete evidence.runs[0].foreground;
  evidence.runs[2].acknowledgements.lostAcknowledgements = 1;
  evidence.runs[4].lifecycle.actions.pop();
  const evaluation = evaluatePhysicalMatrix(evidence);

  assert.equal(evaluation.status, "failed");
  assert.deepEqual(evaluation.requiredRows[0].reasons, [
    "foreground-evidence-missing",
  ]);
  assert.deepEqual(evaluation.requiredRows[2].reasons, [
    "acknowledgement-loss",
  ]);
  assert.deepEqual(evaluation.requiredRows[4].reasons, [
    "lifecycle-action-missing:route-interruption",
  ]);
});


test("CLI emits deterministic JSON and status-specific exit codes", () => {
  const directory = mkdtempSync(join(tmpdir(), "lmdj-web-gate-"));
  try {
    const passedPath = join(directory, "passed.json");
    writeFileSync(passedPath, JSON.stringify(passingEvidence()));
    const passed = spawnSync(
      process.execPath,
      ["src/evaluate-physical-evidence.mjs", passedPath],
      { cwd: new URL("..", import.meta.url), encoding: "utf8" },
    );
    assert.equal(passed.status, 0, passed.stderr);
    assert.equal(JSON.parse(passed.stdout).status, "passed");

    const unverifiedPath = join(directory, "unverified.json");
    writeFileSync(unverifiedPath, JSON.stringify({ evidenceVersion: 1, runs: [] }));
    const unverified = spawnSync(
      process.execPath,
      ["src/evaluate-physical-evidence.mjs", unverifiedPath],
      { cwd: new URL("..", import.meta.url), encoding: "utf8" },
    );
    assert.equal(unverified.status, 2, unverified.stderr);
    assert.equal(JSON.parse(unverified.stdout).status, "unverified");
  } finally {
    rmSync(directory, { recursive: true });
  }
});
