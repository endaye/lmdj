import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import test from "node:test";

import {
  DEADLINES_MS,
  HOST_NOTIFICATIONS,
  HOST_OPERATIONS,
  MAX_ASSET_BYTES,
  MAX_ENVELOPE_BYTES,
  MAX_SAMPLE_IMPORT_BYTES,
  PROTOCOL_VERSION,
  HostProtocolError,
  createProtocolTransport,
  createRequestEnvelope,
  deadlineForOperation,
  decodeRequestEnvelope,
  validateNotificationEnvelope,
  validateResponseEnvelope,
  verifyAssetSidecar,
} from "../web/protocol.mjs";

const REQUEST_ID = "01234567-89ab-cdef-0123-456789abcdef";

function request(overrides = {}) {
  return {
    protocol_version: PROTOCOL_VERSION,
    request_id: REQUEST_ID,
    operation: "host.status",
    payload: {},
    ...overrides,
  };
}

function encode(value) {
  return new TextEncoder().encode(JSON.stringify(value));
}

function encodedRequestAtSize(size) {
  const value = request({ payload: { padding: "" } });
  const baseSize = encode(value).byteLength;
  assert.ok(baseSize <= size);
  value.payload.padding = "x".repeat(size - baseSize);
  const bytes = encode(value);
  assert.equal(bytes.byteLength, size);
  return bytes;
}

function responseAtSize(size) {
  const value = {
    protocol_version: PROTOCOL_VERSION,
    request_id: REQUEST_ID,
    ok: true,
    result: { padding: "" },
  };
  const baseSize = encode(value).byteLength;
  assert.ok(baseSize <= size);
  const remainingBytes = size - baseSize;
  value.result.padding =
    "界".repeat(Math.floor(remainingBytes / 3)) +
    "x".repeat(remainingBytes % 3);
  assert.equal(encode(value).byteLength, size);
  return value;
}

function notificationAtSize(size) {
  const value = {
    protocol_version: PROTOCOL_VERSION,
    event: "runtime.warning",
    payload: { padding: "" },
  };
  const baseSize = encode(value).byteLength;
  assert.ok(baseSize <= size);
  const remainingBytes = size - baseSize;
  value.payload.padding =
    "界".repeat(Math.floor(remainingBytes / 3)) +
    "x".repeat(remainingBytes % 3);
  assert.equal(encode(value).byteLength, size);
  return value;
}

function requestIdFor(index) {
  return `00000000-0000-0000-0000-${String(index).padStart(12, "0")}`;
}

async function sha256Hex(bytes) {
  const digest = await webcrypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, "0"),
  ).join("");
}

function expectCode(code) {
  return (error) => error instanceof HostProtocolError && error.code === code;
}

test("exports the locked protocol constants, operations, and notifications", () => {
  assert.equal(PROTOCOL_VERSION, 1);
  assert.equal(MAX_ENVELOPE_BYTES, 65_536);
  assert.equal(MAX_ASSET_BYTES, 1_048_576);
  assert.equal(MAX_SAMPLE_IMPORT_BYTES, 68_157_440);
  assert.deepEqual(DEADLINES_MS, {
    short: 1_000,
    project: 30_000,
    close: 10_000,
  });
  assert.deepEqual(HOST_OPERATIONS, [
    "host.status",
    "project.create",
    "project.open",
    "project.inspect",
    "project.list",
    "project.import.begin",
    "project.import.index",
    "project.import.entry",
    "project.import.commit",
    "project.import.abort",
    "asset.import",
    "pad.assign",
    "pattern.create",
    "pattern.slot.assign",
    "pattern.slot.clear",
    "pattern.slot.move",
    "performance.list",
    "performance.inspect",
    "performance.record.begin",
    "performance.record.event",
    "performance.record.launch-request",
    "performance.record.flush",
    "performance.record.stop",
    "performance.record.status",
    "performance.save",
    "performance.discard",
    "performance.recovery.list",
    "performance.recovery.apply",
    "performance.recovery.discard",
    "performance.rename",
    "performance.delete",
    "performance.recording.bind",
    "performance.replay.begin",
    "performance.replay.stop",
    "performance.replay.status",
    "performance.resample.commit",
    "snapshot.reload",
    "snapshot.retry",
    "sample.inspect",
    "sample.quota",
    "sample.waveform",
    "sample.import.begin",
    "sample.import.chunk",
    "sample.import.commit",
    "sample.import.abort",
    "sample.update_pad",
    "sample.reset_pad",
    "sample.preview.set",
    "sample.preview.clear",
    "sample.stop",
    "audio.activate",
    "audio.suspend",
    "trigger",
    "sequence.record.begin",
    "sequence.capture.disarm",
    "sequence.record.event",
    "sequence.record.flush",
    "sequence.record.stop",
    "sequence.record.switch-request",
    "sequence.record.status",
    "sequence.settings.update",
    "sequence.recovery.list",
    "sequence.recovery.apply",
    "sequence.recovery.discard",
    "host.close",
  ]);
  assert.deepEqual(HOST_NOTIFICATIONS, [
    "host.state_changed",
    "snapshot.published",
    "snapshot.rejected",
    "audio.interrupted",
    "audio.recovered",
    "midi.connected",
    "midi.disconnected",
    "runtime.warning",
    "runtime.trigger_outcomes",
    "runtime.voice_state",
    "sequence.bar_boundary",
    "capture.sealed",
  ]);
});

test("accepts only exact privacy-safe Sample operation payloads", () => {
  const playback = {
    trim_start_frame: 12,
    trim_end_frame: 48,
    trigger_mode: "loop_gate",
    gain_millidb: -1200,
    muted: false,
  };
  const sampleRequests = [
    ["sample.inspect", {slot: {bank: 0, pad: 3}}],
    ["sample.waveform", {
      slot: {bank: 0, pad: 3},
      window: {start_frame: 0, end_frame: 64, bucket_count: 16},
    }],
    ["sample.import.begin", {
      import_token: requestIdFor(101),
      command_id: requestIdFor(102),
      expected_revision: 7,
      slot: {bank: 0, pad: 3},
      asset_id: requestIdFor(103),
      byte_length: 44,
    }],
    ["sample.import.begin", {
      import_token: requestIdFor(111),
      command_id: requestIdFor(112),
      expected_revision: 7,
      sequence_session_id: requestIdFor(113),
      slot: {bank: 0, pad: 3},
      asset_id: requestIdFor(114),
      byte_length: 44,
    }],
    ["sample.import.chunk", {
      import_token: requestIdFor(101),
      offset: 0,
      final: true,
      sidecar: {sidecar_bytes: 44, sidecar_sha256: "a".repeat(64)},
    }],
    ["sample.import.commit", {import_token: requestIdFor(101)}],
    ["sample.import.abort", {import_token: requestIdFor(101)}],
    ["sample.update_pad", {
      command_id: requestIdFor(104),
      expected_revision: 7,
      slot: {bank: 0, pad: 3},
      playback,
    }],
    ["sample.reset_pad", {
      command_id: requestIdFor(105),
      expected_revision: 7,
      slot: {bank: 0, pad: 3},
    }],
    ["sample.preview.set", {slot: {bank: 0, pad: 3}, playback}],
    ["sample.preview.clear", {slot: {bank: 0, pad: 3}}],
    ["sample.stop", {slot: {bank: 0, pad: 3}}],
    ["sample.stop", {}],
    ["snapshot.retry", {pattern_id: requestIdFor(106)}],
    ["trigger", {slot: 3, kind: "release"}],
  ];
  for (const [operation, payload] of sampleRequests) {
    assert.equal(
      createRequestEnvelope({
        operation,
        payload,
        crypto: {randomUUID: () => REQUEST_ID},
      }).operation,
      operation,
    );
  }

  for (const [operation, payload] of sampleRequests.filter(
    ([candidate]) => candidate.startsWith("sample.") || candidate === "snapshot.retry",
  )) {
    assert.throws(
      () => createRequestEnvelope({
        operation,
        payload: {...payload, project_path: "/forbidden/project.lmdj"},
        crypto: {randomUUID: () => REQUEST_ID},
      }),
      expectCode("HOST_PROTOCOL_MISMATCH"),
    );
  }
  assert.throws(
    () => createRequestEnvelope({
      operation: "sample.import.chunk",
      payload: {
        import_token: requestIdFor(101),
        offset: 0,
        final: true,
        sidecar: {sidecar_bytes: 4, sidecar_sha256: "a".repeat(64)},
        bytes: [1, 2, 3, 4],
      },
      crypto: {randomUUID: () => REQUEST_ID},
    }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("strictly decodes UTF-8 and rejects malformed input", () => {
  assert.throws(
    () => decodeRequestEnvelope(Uint8Array.from([0xc3, 0x28])),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("rejects non-lowercase UUIDs and duplicate request IDs", () => {
  assert.throws(
    () =>
      decodeRequestEnvelope(
        encode(request({ request_id: REQUEST_ID.toUpperCase() })),
      ),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );

  const seenRequestIds = new Set();
  decodeRequestEnvelope(encode(request()), { seenRequestIds });
  assert.throws(
    () => decodeRequestEnvelope(encode(request()), { seenRequestIds }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("rejects wrong versions, unknown fields, and non-object payloads", () => {
  assert.throws(
    () =>
      decodeRequestEnvelope(
        encode(request({ protocol_version: PROTOCOL_VERSION + 1 })),
      ),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  assert.throws(
    () => decodeRequestEnvelope(encode(request({ extra: true }))),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  assert.throws(
    () => decodeRequestEnvelope(encode(request({ payload: [] }))),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("rejects unknown operations and operations disallowed by current state", () => {
  assert.throws(
    () => decodeRequestEnvelope(encode(request({ operation: "host.unknown" }))),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  assert.throws(
    () =>
      decodeRequestEnvelope(
        encode(request({
          operation: "trigger",
          payload: {slot: 0, velocity: 127},
        })),
        {
        allowOperation: () => false,
        },
      ),
    expectCode("HOST_STATE_INVALID"),
  );
});

test("accepts exactly the maximum JSON bytes and rejects maximum plus one", () => {
  const atLimit = decodeRequestEnvelope(
    encodedRequestAtSize(MAX_ENVELOPE_BYTES),
  );
  assert.equal(atLimit.payload.padding.length > 0, true);
  assert.throws(
    () =>
      decodeRequestEnvelope(encodedRequestAtSize(MAX_ENVELOPE_BYTES + 1)),
    expectCode("WEB_RUNTIME_RESOURCE_LIMIT"),
  );
});

test("validates closed response and notification envelopes", () => {
  assert.deepEqual(
    validateResponseEnvelope({
      protocol_version: PROTOCOL_VERSION,
      request_id: REQUEST_ID,
      ok: true,
      result: { state: "running" },
    }),
    {
      protocol_version: PROTOCOL_VERSION,
      request_id: REQUEST_ID,
      ok: true,
      result: { state: "running" },
    },
  );
  assert.throws(
    () =>
      validateResponseEnvelope({
        protocol_version: PROTOCOL_VERSION,
        request_id: REQUEST_ID,
        ok: true,
        result: {},
        extra: true,
      }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  assert.deepEqual(
    validateNotificationEnvelope({
      protocol_version: PROTOCOL_VERSION,
      event: "audio.interrupted",
      payload: {},
    }),
    {
      protocol_version: PROTOCOL_VERSION,
      event: "audio.interrupted",
      payload: {},
    },
  );
  assert.throws(
    () =>
      validateNotificationEnvelope({
        protocol_version: PROTOCOL_VERSION,
        event: "audio.unknown",
        payload: {},
      }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("bounds response envelopes by exact UTF-8 bytes", () => {
  assert.equal(
    validateResponseEnvelope(responseAtSize(MAX_ENVELOPE_BYTES)).ok,
    true,
  );
  assert.throws(
    () => validateResponseEnvelope(responseAtSize(MAX_ENVELOPE_BYTES + 1)),
    expectCode("WEB_RUNTIME_RESOURCE_LIMIT"),
  );
});

test("bounds notification envelopes by exact UTF-8 bytes", () => {
  assert.equal(
    validateNotificationEnvelope(notificationAtSize(MAX_ENVELOPE_BYTES)).event,
    "runtime.warning",
  );
  assert.throws(
    () =>
      validateNotificationEnvelope(
        notificationAtSize(MAX_ENVELOPE_BYTES + 1),
      ),
    expectCode("WEB_RUNTIME_RESOURCE_LIMIT"),
  );
});

test("creates lowercase request IDs only through injected crypto", () => {
  const envelope = createRequestEnvelope({
    operation: "host.status",
    payload: {},
    crypto: { randomUUID: () => REQUEST_ID },
  });
  assert.deepEqual(envelope, request());
  assert.throws(
    () =>
      createRequestEnvelope({
        operation: "host.status",
        payload: {},
        crypto: { randomUUID: () => REQUEST_ID.toUpperCase() },
      }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("uses exact operation-class deadlines", () => {
  for (const operation of [
    "host.status",
    "audio.activate",
    "audio.suspend",
    "trigger",
    "sample.preview.set",
    "sample.preview.clear",
    "sample.stop",
    "sequence.record.event",
    "sequence.record.status",
    "sequence.recovery.list",
    "performance.record.event",
    "performance.record.launch-request",
    "performance.record.status",
    "performance.recovery.list",
    "performance.replay.status",
  ]) {
    assert.equal(deadlineForOperation(operation), DEADLINES_MS.short);
  }
  for (const operation of HOST_OPERATIONS.filter(
    (operation) =>
      operation !== "host.close" &&
      ![
        "host.status",
        "audio.activate",
        "audio.suspend",
        "trigger",
        "sample.preview.set",
        "sample.preview.clear",
        "sample.stop",
        "sequence.record.event",
        "sequence.record.status",
        "sequence.recovery.list",
        "performance.record.event",
        "performance.record.launch-request",
        "performance.record.status",
        "performance.recovery.list",
        "performance.replay.status",
      ].includes(
        operation,
      ),
  )) {
    assert.equal(deadlineForOperation(operation), DEADLINES_MS.project);
  }
  assert.equal(deadlineForOperation("host.close"), DEADLINES_MS.close);
});

test("verifies asset sidecar length and SHA-256 using injected crypto", async () => {
  const sidecar = Uint8Array.from([1, 2, 3, 4]);
  const declaration = {
    sidecar_bytes: sidecar.byteLength,
    sidecar_sha256: await sha256Hex(sidecar),
  };
  await assert.doesNotReject(
    verifyAssetSidecar(declaration, sidecar, { crypto: webcrypto }),
  );
  await assert.rejects(
    verifyAssetSidecar({ ...declaration, sidecar_bytes: 3 }, sidecar, {
      crypto: webcrypto,
    }),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  await assert.rejects(
    verifyAssetSidecar(
      { ...declaration, sidecar_sha256: "0".repeat(64) },
      sidecar,
      { crypto: webcrypto },
    ),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
});

test("rejects an asset sidecar above the exact import limit", async () => {
  await assert.rejects(
    verifyAssetSidecar(
      { sidecar_bytes: MAX_ASSET_BYTES + 1, sidecar_sha256: "0".repeat(64) },
      new Uint8Array(MAX_ASSET_BYTES + 1),
      { crypto: webcrypto },
    ),
    expectCode("WEB_RUNTIME_RESOURCE_LIMIT"),
  );
});

test("accepts one verified Sample chunk sidecar at the exact import limit", async () => {
  const sidecar = new Uint8Array(MAX_ASSET_BYTES);
  sidecar[0] = 0x52;
  sidecar[MAX_ASSET_BYTES - 1] = 0x7f;
  const declaration = {
    sidecar_bytes: MAX_ASSET_BYTES,
    sidecar_sha256: await sha256Hex(sidecar),
  };
  await assert.doesNotReject(
    verifyAssetSidecar(declaration, sidecar, {crypto: webcrypto}),
  );
});

test("a deadline terminates transport and ignores a later mutation response", async () => {
  let monotonicNow = 10_000;
  let terminated = 0;
  const sent = [];
  const timers = [];
  const setTimer = (callback, delay) => {
    const timer = { callback, due: monotonicNow + delay, active: true };
    timers.push(timer);
    return timer;
  };
  const clearTimer = (timer) => {
    timer.active = false;
  };
  const advance = (milliseconds) => {
    monotonicNow += milliseconds;
    for (const timer of timers) {
      if (timer.active && timer.due <= monotonicNow) {
        timer.active = false;
        timer.callback();
      }
    }
  };
  const transport = createProtocolTransport({
    send: (envelope) => sent.push(envelope),
    terminate: () => {
      terminated += 1;
    },
    now: () => monotonicNow,
    setTimer,
    clearTimer,
  });
  const envelope = request({ operation: "project.create" });
  const pending = transport.request(envelope);
  assert.deepEqual(sent, [envelope]);

  advance(DEADLINES_MS.project);
  await assert.rejects(pending, expectCode("HOST_TIMEOUT"));
  assert.equal(terminated, 1);
  assert.equal(transport.terminated, true);
  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: REQUEST_ID,
      ok: true,
      result: { project_revision: 2 },
    }),
    false,
  );
  assert.equal(transport.pendingCount, 0);
  assert.equal(transport.activeRequestIdCount, 0);
});

test("a response arriving after its monotonic deadline fails closed", async () => {
  let monotonicNow = 0;
  let terminateCalls = 0;
  const transport = createProtocolTransport({
    send: () => {},
    terminate: () => {
      terminateCalls += 1;
    },
    now: () => monotonicNow,
    setTimer: () => ({ active: true }),
    clearTimer: (timer) => {
      timer.active = false;
    },
  });
  const pending = transport.request(request());
  monotonicNow = DEADLINES_MS.short;
  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: REQUEST_ID,
      ok: true,
      result: {},
    }),
    false,
  );
  await assert.rejects(pending, expectCode("HOST_TIMEOUT"));
  assert.equal(terminateCalls, 1);
  assert.equal(transport.activeRequestIdCount, 0);
});

test("a malformed response atomically fails closed and later replies have no effect", async () => {
  let terminateCalls = 0;
  let appliedMutations = 0;
  let stateObservedByTerminate = null;
  const timers = [];
  let transport;
  transport = createProtocolTransport({
    send: () => {},
    terminate: () => {
      terminateCalls += 1;
      stateObservedByTerminate = {
        pendingCount: transport.pendingCount,
        activeRequestIdCount: transport.activeRequestIdCount,
        activeTimerCount: timers.filter(({ active }) => active).length,
      };
    },
    now: () => 0,
    setTimer: () => {
      const timer = { active: true };
      timers.push(timer);
      return timer;
    },
    clearTimer: (timer) => {
      timer.active = false;
    },
  });
  const first = transport.request(
    request({ request_id: requestIdFor(1), operation: "project.create" }),
  );
  const second = transport.request(
    request({ request_id: requestIdFor(2), operation: "project.open" }),
  );
  first.then(
    () => {
      appliedMutations += 1;
    },
    () => {},
  );
  second.then(
    () => {
      appliedMutations += 1;
    },
    () => {},
  );

  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: requestIdFor(1),
      ok: true,
      result: { project_revision: 2 },
      extra: true,
    }),
    false,
  );
  await assert.rejects(first, expectCode("HOST_PROTOCOL_MISMATCH"));
  await assert.rejects(second, expectCode("HOST_PROTOCOL_MISMATCH"));
  assert.equal(transport.terminated, true);
  assert.equal(terminateCalls, 1);
  assert.equal(transport.pendingCount, 0);
  assert.equal(transport.activeRequestIdCount, 0);
  assert.equal(timers.every(({ active }) => active === false), true);
  assert.deepEqual(stateObservedByTerminate, {
    pendingCount: 0,
    activeRequestIdCount: 0,
    activeTimerCount: 0,
  });

  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: requestIdFor(1),
      ok: true,
      result: { project_revision: 2 },
    }),
    false,
  );
  await Promise.resolve();
  assert.equal(appliedMutations, 0);
});

test("an unknown response request ID atomically fails closed", async () => {
  let terminateCalls = 0;
  const transport = createProtocolTransport({
    send: () => {},
    terminate: () => {
      terminateCalls += 1;
    },
    now: () => 0,
    setTimer: () => ({ active: true }),
    clearTimer: (timer) => {
      timer.active = false;
    },
  });
  const first = transport.request(request({ request_id: requestIdFor(1) }));
  const second = transport.request(request({ request_id: requestIdFor(2) }));

  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: requestIdFor(3),
      ok: true,
      result: {},
    }),
    false,
  );
  assert.equal(transport.terminated, true);
  await assert.rejects(first, expectCode("HOST_PROTOCOL_MISMATCH"));
  await assert.rejects(second, expectCode("HOST_PROTOCOL_MISMATCH"));
  assert.equal(transport.terminated, true);
  assert.equal(terminateCalls, 1);
  assert.equal(transport.pendingCount, 0);
  assert.equal(transport.activeRequestIdCount, 0);
});

test("a duplicate response after settlement atomically fails closed", async () => {
  let terminateCalls = 0;
  const transport = createProtocolTransport({
    send: () => {},
    terminate: () => {
      terminateCalls += 1;
    },
    now: () => 0,
    setTimer: () => ({ active: true }),
    clearTimer: (timer) => {
      timer.active = false;
    },
  });
  const first = transport.request(request({ request_id: requestIdFor(1) }));
  const second = transport.request(request({ request_id: requestIdFor(2) }));
  const response = {
    protocol_version: PROTOCOL_VERSION,
    request_id: requestIdFor(1),
    ok: true,
    result: { settled: true },
  };

  assert.equal(transport.receive(response), true);
  assert.deepEqual(await first, { settled: true });
  assert.equal(transport.receive(response), false);
  assert.equal(transport.terminated, true);
  await assert.rejects(second, expectCode("HOST_PROTOCOL_MISMATCH"));
  assert.equal(transport.terminated, true);
  assert.equal(terminateCalls, 1);
  assert.equal(transport.pendingCount, 0);
  assert.equal(transport.activeRequestIdCount, 0);
});

test("request identity storage stays bounded and completed IDs may be reused", async () => {
  const transport = createProtocolTransport({
    send: () => {},
    terminate: () => {},
    now: () => 0,
    setTimer: () => ({ active: true }),
    clearTimer: (timer) => {
      timer.active = false;
    },
  });

  for (let index = 0; index < 512; index += 1) {
    const request_id = requestIdFor(index);
    const pending = transport.request(request({ request_id }));
    assert.equal(
      transport.receive({
        protocol_version: PROTOCOL_VERSION,
        request_id,
        ok: true,
        result: { index },
      }),
      true,
    );
    assert.deepEqual(await pending, { index });
    assert.equal(transport.activeRequestIdCount, 0);
  }

  const reused = transport.request(request({ request_id: requestIdFor(0) }));
  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: requestIdFor(0),
      ok: true,
      result: { reused: true },
    }),
    true,
  );
  assert.deepEqual(await reused, { reused: true });
  assert.equal(transport.activeRequestIdCount, 0);
});

test("duplicate request IDs remain rejected while the first request is in flight", async () => {
  const transport = createProtocolTransport({
    send: () => {},
    terminate: () => {},
    now: () => 0,
    setTimer: () => ({ active: true }),
    clearTimer: (timer) => {
      timer.active = false;
    },
  });
  const pending = transport.request(request());
  assert.throws(
    () => transport.request(request()),
    expectCode("HOST_PROTOCOL_MISMATCH"),
  );
  assert.equal(
    transport.receive({
      protocol_version: PROTOCOL_VERSION,
      request_id: REQUEST_ID,
      ok: true,
      result: {},
    }),
    true,
  );
  await assert.doesNotReject(pending);
});
