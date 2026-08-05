import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

import {
  DIAGNOSTIC_PROJECT_CONTRACT,
  DIAGNOSTIC_PROJECT_STORAGE_KEY,
  createDiagnosticProjectCoordinator,
  createDiagnosticWav,
  loadOrCreateDiagnosticDescriptor,
} from "../src/diagnostic_project.mjs";

const PROJECT_ID = "00000000-0000-4000-8000-000000000001";
const PATTERN_ID = "00000000-0000-4000-8000-000000000002";
const ASSET_ID = "00000000-0000-4000-8000-000000000003";

function descriptor() {
  return {
    contract: DIAGNOSTIC_PROJECT_CONTRACT,
    project_id: PROJECT_ID,
    pattern_id: PATTERN_ID,
    asset_id: ASSET_ID,
  };
}

function uuidSource() {
  let next = 1;
  return {
    randomUUID() {
      const suffix = String(next).padStart(12, "0");
      next += 1;
      return `00000000-0000-4000-4000-${suffix}`;
    },
    subtle: webcrypto.subtle,
  };
}

function memoryStorage(initial = undefined) {
  const values = new Map(
    initial === undefined ? [] : [[DIAGNOSTIC_PROJECT_STORAGE_KEY, initial]],
  );
  return {
    getItem(key) {
      return values.get(key) ?? null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    value() {
      return values.get(DIAGNOSTIC_PROJECT_STORAGE_KEY) ?? null;
    },
  };
}

function emptyProject({ assetPresent = false, assignments = {} } = {}) {
  return {
    assets: assetPresent ? { [ASSET_ID]: { artifact: {} } } : {},
    banks: Array.from({ length: 4 }, (_, bank) => ({
      bank,
      pads: Array.from({ length: 16 }, (_, pad) => ({
        pad,
        asset_id: assignments[bank * 16 + pad] ?? null,
      })),
    })),
  };
}

function scriptedTransport(entries) {
  const calls = [];
  return {
    calls,
    async send(request, options) {
      calls.push({ request, options });
      const entry = entries.shift();
      assert.ok(entry, `unexpected request: ${request.operation}`);
      assert.equal(request.operation, entry.operation);
      if (entry.verify) {
        entry.verify(request, options);
      }
      if (entry.error) {
        throw Object.assign(new Error(entry.error.code), entry.error);
      }
      return entry.result;
    },
    assertDrained() {
      assert.equal(entries.length, 0, "all scripted requests were consumed");
    },
  };
}

function inspector(project, projectRevision) {
  return { project, project_revision: projectRevision };
}

function freshEntries() {
  return [
    { operation: "project.open", error: { code: "NOT_FOUND" } },
    {
      operation: "project.create",
      result: { project_revision: 0 },
      verify({ payload }) {
        assert.deepEqual(payload, {
          project_id: PROJECT_ID,
          bpm: 120,
          initial_pattern: { pattern_id: PATTERN_ID, bars: 1, events: [] },
        });
      },
    },
    { operation: "project.inspect", result: inspector(emptyProject(), 0) },
    {
      operation: "asset.import",
      result: { project_revision: 1 },
      verify({ payload }, { deadlineMs, sidecar }) {
        assert.equal(deadlineMs, 30_000);
        assert.equal(payload.asset_id, ASSET_ID);
        assert.equal(payload.expected_revision, 0);
        assert.equal(payload.media_type, "audio/wav");
        assert.equal(payload.sidecar.sidecar_bytes, sidecar.byteLength);
        assert.match(payload.sidecar.sidecar_sha256, /^[0-9a-f]{64}$/);
        assert.deepEqual(sidecar, createDiagnosticWav());
      },
    },
    ...Array.from({ length: 64 }, (_, index) => ({
      operation: "pad.assign",
      result: { project_revision: index + 2 },
      verify({ payload }) {
        assert.equal(payload.expected_revision, index + 1);
        assert.deepEqual(payload.slot, {
          bank: Math.floor(index / 16),
          pad: index % 16,
        });
        assert.equal(payload.asset_id, ASSET_ID);
      },
    })),
    {
      operation: "snapshot.reload",
      result: { runtime_ready: true, generation: 1 },
      verify({ payload }) {
        assert.deepEqual(payload, { pattern_id: PATTERN_ID });
      },
    },
  ];
}

function coordinator({ entries, storage = memoryStorage(JSON.stringify(descriptor())) } = {}) {
  const transport = scriptedTransport(entries);
  return {
    transport,
    coordinator: createDiagnosticProjectCoordinator({
      storage,
      crypto: uuidSource(),
      transport,
    }),
  };
}

test("creates exactly the versioned locator and deterministic bounded mono WAV", () => {
  const storage = memoryStorage();
  const crypto = uuidSource();
  const value = loadOrCreateDiagnosticDescriptor({ storage, crypto });

  assert.deepEqual(Object.keys(value).sort(), [
    "asset_id",
    "contract",
    "pattern_id",
    "project_id",
  ]);
  assert.equal(value.contract, DIAGNOSTIC_PROJECT_CONTRACT);
  assert.equal(DIAGNOSTIC_PROJECT_STORAGE_KEY, DIAGNOSTIC_PROJECT_CONTRACT);
  assert.deepEqual(JSON.parse(storage.value()), value);

  const wav = createDiagnosticWav();
  assert.equal(new TextDecoder().decode(wav.slice(0, 4)), "RIFF");
  assert.equal(new TextDecoder().decode(wav.slice(8, 12)), "WAVE");
  assert.equal(new DataView(wav.buffer).getUint16(22, true), 1);
  assert.equal(new DataView(wav.buffer).getUint32(24, true), 48_000);
  assert.equal(new DataView(wav.buffer).getUint16(34, true), 16);
  assert.ok(wav.byteLength < 1_048_576);
  assert.deepEqual(createDiagnosticWav(), wav);
});

test("reuses only a valid exact locator and replaces malformed values before transport requests", () => {
  const valid = descriptor();
  const values = [
    JSON.stringify(valid),
    "{",
    JSON.stringify({ ...valid, contract: "wrong" }),
    JSON.stringify({ ...valid, extra: true }),
    JSON.stringify({ ...valid, project_id: "not-a-uuid" }),
  ];

  for (const value of values) {
    const storage = memoryStorage(value);
    const result = loadOrCreateDiagnosticDescriptor({ storage, crypto: uuidSource() });
    if (value === JSON.stringify(valid)) {
      assert.deepEqual(result, valid);
    } else {
      assert.notDeepEqual(result, valid);
      assert.deepEqual(Object.keys(result).sort(), [
        "asset_id",
        "contract",
        "pattern_id",
        "project_id",
      ]);
      assert.equal(result.contract, DIAGNOSTIC_PROJECT_CONTRACT);
      assert.deepEqual(JSON.parse(storage.value()), result);
    }
  }
});

test("fresh preparation creates, inspects, imports, assigns all pads, and publishes", async () => {
  const { coordinator: subject, transport } = coordinator({ entries: freshEntries() });

  const result = await subject.load();

  assert.deepEqual(result, { state: "ready", generation: 1 });
  assert.deepEqual(subject.diagnostics(), {
    diagnostic_project_state: "ready",
    diagnostic_project_generation: 1,
  });
  assert.equal(transport.calls.length, 69);
  transport.assertDrained();
});

test("an existing correct project only opens, inspects, and republishes", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 3 } },
    ],
  });

  assert.deepEqual(await subject.load(), { state: "ready", generation: 3 });
  assert.deepEqual(transport.calls.map(({ request }) => request.operation), [
    "project.open",
    "project.inspect",
    "snapshot.reload",
  ]);
  transport.assertDrained();
});

test("a partial project imports only an absent asset and repairs only wrong pad slots", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  assignments[1] = null;
  assignments[47] = "00000000-0000-4000-8000-000000000099";
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assignments }), 65) },
      { operation: "asset.import", result: { project_revision: 66 } },
      {
        operation: "pad.assign",
        result: { project_revision: 67 },
        verify({ payload }) {
          assert.equal(payload.expected_revision, 66);
          assert.deepEqual(payload.slot, { bank: 0, pad: 1 });
        },
      },
      {
        operation: "pad.assign",
        result: { project_revision: 68 },
        verify({ payload }) {
          assert.equal(payload.expected_revision, 67);
          assert.deepEqual(payload.slot, { bank: 2, pad: 15 });
        },
      },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 4 } },
    ],
  });

  assert.deepEqual(await subject.load(), { state: "ready", generation: 4 });
  transport.assertDrained();
});

test("a duplicate creation race reopens then repairs authoritative truth", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", error: { code: "NOT_FOUND" } },
      { operation: "project.create", error: { code: "DUPLICATE_ID" } },
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 5 } },
    ],
  });

  assert.deepEqual(await subject.load(), { state: "ready", generation: 5 });
  assert.deepEqual(transport.calls.map(({ request }) => request.operation), [
    "project.open", "project.create", "project.open", "project.inspect", "snapshot.reload",
  ]);
  transport.assertDrained();
});

test("concurrent calls share one preparation and one public result", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 6 } },
    ],
  });

  const first = subject.load();
  const second = subject.load();
  assert.strictEqual(first, second);
  assert.deepEqual(await first, { state: "ready", generation: 6 });
  assert.equal(transport.calls.length, 3);
  transport.assertDrained();
});

test("a typed pre-publication error is retryable from authoritative truth", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 0 } },
      { operation: "project.inspect", result: inspector(emptyProject(), 0) },
      { operation: "asset.import", error: { code: "WEB_RUNTIME_RESOURCE_LIMIT" } },
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 7 } },
    ],
  });

  assert.deepEqual(await subject.load(), {
    state: "error",
    error_code: "WEB_RUNTIME_RESOURCE_LIMIT",
  });
  assert.deepEqual(subject.diagnostics(), {
    diagnostic_project_state: "error",
    diagnostic_project_error_code: "WEB_RUNTIME_RESOURCE_LIMIT",
  });
  assert.deepEqual(await subject.load(), { state: "ready", generation: 7 });
  transport.assertDrained();
});

test("restart-required preserves an unknown outcome and never retries automatically", async () => {
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 0 } },
      { operation: "project.inspect", result: inspector(emptyProject(), 0) },
      { operation: "asset.import", error: { code: "HOST_RESTART_REQUIRED" } },
    ],
  });

  assert.deepEqual(await subject.load(), {
    state: "restart-required",
    outcome: "unknown",
  });
  assert.deepEqual(subject.diagnostics(), {
    diagnostic_project_state: "restart-required",
    diagnostic_project_error_code: "HOST_RESTART_REQUIRED",
  });
  assert.equal(transport.calls.length, 3);
  transport.assertDrained();
});

test("pagehide invalidation prevents late readiness and forces a later reopen", async () => {
  let releaseReload;
  const reload = new Promise((resolve) => {
    releaseReload = resolve;
  });
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject, transport } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: reload },
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 9 } },
    ],
  });

  const first = subject.load();
  subject.invalidate();
  releaseReload({ runtime_ready: true, generation: 8 });
  assert.deepEqual(await first, { state: "error" });
  assert.deepEqual(subject.diagnostics(), { diagnostic_project_state: "error" });
  assert.deepEqual(await subject.load(), { state: "ready", generation: 9 });
  transport.assertDrained();
});

test("public results and diagnostics never disclose descriptor UUIDs", async () => {
  const assignments = Object.fromEntries(Array.from({ length: 64 }, (_, index) => [index, ASSET_ID]));
  const { coordinator: subject } = coordinator({
    entries: [
      { operation: "project.open", result: { project_revision: 65 } },
      { operation: "project.inspect", result: inspector(emptyProject({ assetPresent: true, assignments }), 65) },
      { operation: "snapshot.reload", result: { runtime_ready: true, generation: 10 } },
    ],
  });

  const result = await subject.load();
  const publicValues = `${JSON.stringify(result)}${JSON.stringify(subject.diagnostics())}`;
  for (const id of [PROJECT_ID, PATTERN_ID, ASSET_ID]) {
    assert.equal(publicValues.includes(id), false);
  }
});
