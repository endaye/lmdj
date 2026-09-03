import assert from "node:assert/strict";
import test from "node:test";

import {
  HOST_OPERATIONS,
  PROTOCOL_VERSION,
  HostProtocolError,
  createProtocolTransport,
  createRequestEnvelope,
  validateResponseEnvelope,
} from "../web/protocol.mjs";

const ids = Array.from({length: 40}, (_, index) =>
  `00000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`);
const sha = "a".repeat(64);

const PERFORMANCE_OPERATIONS = Object.freeze([
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
]);

function request(operation, payload, outerId = ids[0]) {
  return createRequestEnvelope({
    operation,
    payload,
    crypto: {randomUUID: () => outerId},
  });
}

function expectProtocolMismatch(callback) {
  assert.throws(callback, (error) =>
    error instanceof HostProtocolError &&
    error.code === "HOST_PROTOCOL_MISMATCH");
}

function validRequests() {
  const eventBase = {gesture_id: ids[4]};
  return [
    ["pattern.slot.assign", {command_id: ids[1], expected_revision: 2, pattern_slot: 3, pattern_id: ids[2]}],
    ["pattern.slot.clear", {command_id: ids[1], expected_revision: 2, pattern_slot: 3}],
    ["pattern.slot.move", {command_id: ids[1], expected_revision: 2, from_slot: 3, to_slot: 4}],
    ["performance.list", {}],
    ["performance.inspect", {performance_id: ids[2]}],
    ["performance.record.begin", {command_id: ids[1], expected_revision: 2, session_id: ids[2], performance_id: ids[3]}],
    ...[
      {...eventBase, kind: "pad_press", slot: 7, velocity: 100},
      {...eventBase, kind: "pad_release", slot: 7},
      {...eventBase, kind: "fx_engage", fx: "filter", value: 500},
      {...eventBase, kind: "fx_move", fx: "delay", value: 501},
      {...eventBase, kind: "fx_release", fx: "reverb"},
      {kind: "hold_on"},
      {kind: "hold_off"},
    ].map((event) => ["performance.record.event", {
      session_id: ids[2], event_id: ids[3], event,
    }]),
    ["performance.record.launch-request", {session_id: ids[2], request_id: ids[3], pattern_slot: 4}],
    ["performance.record.flush", {session_id: ids[2], command_id: ids[3]}],
    ["performance.record.stop", {session_id: ids[2], request_id: ids[3]}],
    ["performance.record.status", {}],
    ["performance.save", {command_id: ids[1], expected_revision: 2, performance_id: ids[2], name: "Take 1", recording_artifact: null}],
    ["performance.discard", {command_id: ids[1], expected_revision: 2, performance_id: ids[2]}],
    ["performance.recovery.list", {}],
    ["performance.recovery.apply", {command_id: ids[1], expected_revision: 2, session_id: ids[2]}],
    ["performance.recovery.discard", {session_id: ids[2], request_id: ids[3]}],
    ["performance.rename", {command_id: ids[1], expected_revision: 2, performance_id: ids[2], name: "Renamed"}],
    ["performance.delete", {command_id: ids[1], expected_revision: 2, performance_id: ids[2]}],
    ["performance.recording.bind", {command_id: ids[1], expected_revision: 2, performance_id: ids[2], recording_artifact: {sha256: sha, media_type: "audio/wav", byte_length: 44}}],
    ["performance.replay.begin", {replay_id: ids[1], performance_id: ids[2]}],
    ["performance.replay.stop", {replay_id: ids[1], request_id: ids[2]}],
    ["performance.replay.status", {replay_id: ids[1]}],
    ["performance.resample.commit", {command_id: ids[1], expected_revision: 2, performance_id: ids[2], source_start_frame: 0, source_end_frame: 48_000, target_slot: {bank: 1, pad: 2}}],
  ];
}

test("locks the complete Performance operation inventory", () => {
  assert.equal(PERFORMANCE_OPERATIONS.length, 23);
  assert.deepEqual(
    HOST_OPERATIONS.filter((operation) =>
      operation.startsWith("performance.") || operation.startsWith("pattern.slot.")),
    PERFORMANCE_OPERATIONS,
  );
  expectProtocolMismatch(() => request(
    "performance.bank.switch", {bank: 1}));
});

test("accepts each strict raw Performance input union and rejects every extra field", () => {
  for (const [operation, payload] of validRequests()) {
    assert.equal(request(operation, payload).operation, operation);
    expectProtocolMismatch(() => request(operation, {...payload, runtime_frame: 1}));
  }
});

test("rejects extras nested inside raw events, Artifacts, and slot addresses", () => {
  expectProtocolMismatch(() => request("performance.record.event", {
    session_id: ids[2],
    event_id: ids[3],
    event: {
      kind: "pad_press", gesture_id: ids[4], slot: 7, velocity: 100,
      runtime_frame: 1,
    },
  }));
  expectProtocolMismatch(() => request("performance.recording.bind", {
    command_id: ids[1], expected_revision: 2, performance_id: ids[2],
    recording_artifact: {
      sha256: sha, media_type: "audio/wav", byte_length: 44,
      bundle_path: "recordings/take.wav",
    },
  }));
  expectProtocolMismatch(() => request("performance.resample.commit", {
    command_id: ids[1], expected_revision: 2, performance_id: ids[2],
    source_start_frame: 0, source_end_frame: 48_000,
    target_slot: {bank: 1, pad: 2, flat_slot: 18},
  }));
});

test("counts Performance names in Unicode code points at the 64 point boundary", () => {
  const namedPayload = (operation, name) => operation === "performance.save"
    ? {
        command_id: ids[1], expected_revision: 2, performance_id: ids[2],
        name, recording_artifact: null,
      }
    : {
        command_id: ids[1], expected_revision: 2, performance_id: ids[2], name,
      };
  for (const [operation, unit] of [
    ["performance.save", "演"],
    ["performance.rename", "😀"],
  ]) {
    assert.equal(
      request(operation, namedPayload(operation, unit.repeat(64))).operation,
      operation,
    );
    expectProtocolMismatch(() => request(
      operation,
      namedPayload(operation, unit.repeat(65)),
    ));
  }
});

test("keeps transport, event, request, and gesture identities collision-free", () => {
  expectProtocolMismatch(() => request("performance.record.event", {
    session_id: ids[2], event_id: ids[0],
    event: {kind: "pad_press", gesture_id: ids[4], slot: 1, velocity: 100},
  }));
  expectProtocolMismatch(() => request("performance.record.event", {
    session_id: ids[2], event_id: ids[3],
    event: {kind: "pad_press", gesture_id: ids[3], slot: 1, velocity: 100},
  }));
  expectProtocolMismatch(() => request("performance.record.launch-request", {
    session_id: ids[2], request_id: ids[0], pattern_slot: 1,
  }));
});

const lifecycle = {performance_id: ids[3], committed_revision: 3, replayed: false};
const replay = {replay_id: ids[1], state: "playing", resolved_revision: 3, event_cursor: 1, event_count: 2};
const status = {
  state: "active", session_id: ids[2], performance_id: ids[3],
  journal_revision: 1, next_flush_seq: 2, pending_event_count: 1,
  open_pad_gestures: 0, open_fx_gestures: 0, hold: false,
  pending_launch: null, last_launch_ack: null,
};

function validResults() {
  const revisioned = new Set([
    "pattern.slot.assign", "pattern.slot.clear", "pattern.slot.move",
    "performance.list", "performance.inspect", "performance.record.begin",
    "performance.record.flush", "performance.save", "performance.discard",
    "performance.recovery.apply", "performance.rename", "performance.delete",
    "performance.recording.bind", "performance.resample.commit",
  ]);
  return new Map([
    ["pattern.slot.assign", {pattern_slot: 1, pattern_id: ids[2], committed_revision: 3, replayed: false}],
    ["pattern.slot.clear", {pattern_slot: 1, pattern_id: null, committed_revision: 3, replayed: false}],
    ["pattern.slot.move", {from_slot: 1, to_slot: 2, pattern_id: ids[2], committed_revision: 3, replayed: false}],
    ["performance.list", {performances: [{performance_id: ids[3], name: "Take 1", created_bpm: 120, recording_artifact: null, event_count: 2}]}],
    ["performance.inspect", {performance: {id: ids[3], name: "Take 1", created_bpm: 120, recording_artifact: null, events: [{kind: "hold_on", tick: 0}, {kind: "hold_off", tick: 960}]}}],
    ["performance.record.begin", lifecycle],
    ["performance.record.event", {event_id: ids[3], accepted_tick: 0, input_sequence: 1, coalesced: false, replayed: false}],
    ["performance.record.launch-request", {request_id: ids[3], state: "pending", target_tick: 3840}],
    ["performance.record.flush", lifecycle],
    ["performance.record.stop", {request_id: ids[3], session_id: ids[2], performance_id: ids[4], state: "stopped", pending_event_count: 0, replayed: false}],
    ["performance.record.status", status],
    ["performance.save", lifecycle],
    ["performance.discard", lifecycle],
    ["performance.recovery.list", {candidates: [{session_id: ids[2], performance_id: ids[3], reason: "owner_lost", durable_event_count: 1, pending_event_count: 0, fingerprint: sha}]}],
    ["performance.recovery.apply", lifecycle],
    ["performance.recovery.discard", {request_id: ids[3], session_id: ids[2], performance_id: ids[4], state: "stopped", pending_event_count: 0, replayed: false}],
    ["performance.rename", lifecycle],
    ["performance.delete", lifecycle],
    ["performance.recording.bind", lifecycle],
    ["performance.replay.begin", replay],
    ["performance.replay.stop", {...replay, request_id: ids[2], replayed: false}],
    ["performance.replay.status", replay],
    ["performance.resample.commit", {performance_id: ids[3], committed_revision: 3, runtime_prepare_required: true}],
  ].map(([operation, result]) => [operation, {
    ...result,
    project_revision: revisioned.has(operation) ? 3 : null,
  }]));
}

test("validates every Performance result projection and rejects result extras", () => {
  const results = validResults();
  assert.deepEqual([...results.keys()], PERFORMANCE_OPERATIONS);
  for (const [operation, result] of results) {
    const envelope = {
      protocol_version: PROTOCOL_VERSION,
      request_id: ids[0],
      ok: true,
      result,
    };
    assert.equal(validateResponseEnvelope(envelope, operation), envelope);
    expectProtocolMismatch(() => validateResponseEnvelope({
      ...envelope,
      result: {...result, runtime_frame: 1},
    }, operation));
  }
});

test("rejects extras nested inside Performance results", () => {
  const response = (operation, result) => ({
    protocol_version: PROTOCOL_VERSION,
    request_id: ids[0],
    ok: true,
    result,
  });
  const results = validResults();
  expectProtocolMismatch(() => validateResponseEnvelope(response(
    "performance.list",
    {
      ...results.get("performance.list"),
      performances: [{
        ...results.get("performance.list").performances[0],
        runtime_frame: 1,
      }],
    },
  ), "performance.list"));
  expectProtocolMismatch(() => validateResponseEnvelope(response(
    "performance.inspect",
    {
      ...results.get("performance.inspect"),
      performance: {
        ...results.get("performance.inspect").performance,
        events: [{kind: "hold_on", tick: 0, input_sequence: 1}],
      },
    },
  ), "performance.inspect"));
  expectProtocolMismatch(() => validateResponseEnvelope(response(
    "performance.record.status",
    {
      ...results.get("performance.record.status"),
      pending_launch: {
        request_id: ids[4], pattern_slot: 2, target_tick: 3840,
        claimed: false, runtime_frame: 1,
      },
    },
  ), "performance.record.status"));
  expectProtocolMismatch(() => validateResponseEnvelope(response(
    "performance.recovery.list",
    {
      ...results.get("performance.recovery.list"),
      candidates: [{
        ...results.get("performance.recovery.list").candidates[0],
        runtime_frame: 1,
      }],
    },
  ), "performance.recovery.list"));
});

test("validates projected Performance names by Unicode code point", () => {
  const response = (operation, result) => ({
    protocol_version: PROTOCOL_VERSION,
    request_id: ids[0],
    ok: true,
    result,
  });
  for (const [operation, unit, select] of [
    ["performance.list", "演", (result) => result.performances[0]],
    ["performance.inspect", "😀", (result) => result.performance],
  ]) {
    const accepted = structuredClone(validResults().get(operation));
    select(accepted).name = unit.repeat(64);
    assert.equal(
      validateResponseEnvelope(response(operation, accepted), operation).result,
      accepted,
    );

    const rejected = structuredClone(accepted);
    select(rejected).name = unit.repeat(65);
    expectProtocolMismatch(() => validateResponseEnvelope(
      response(operation, rejected), operation,
    ));
  }
});

test("transport validates a successful result against its pending operation", async () => {
  let sent;
  const transport = createProtocolTransport({
    send: (envelope) => { sent = envelope; },
    terminate() {},
    now: () => 0,
    setTimer: () => 1,
    clearTimer() {},
  });
  const pending = transport.request(request("performance.record.status", {}));
  assert.equal(transport.receive({
    protocol_version: PROTOCOL_VERSION,
    request_id: sent.request_id,
    ok: true,
    result: {...status, effective_tick: 1},
  }), false);
  await assert.rejects(pending, (error) =>
    error instanceof HostProtocolError &&
    error.code === "HOST_PROTOCOL_MISMATCH");
});
