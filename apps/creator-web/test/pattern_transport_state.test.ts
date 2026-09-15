import {expect, test} from "vitest";

import {
  initialPatternTransportState,
  reducePatternTransport,
  selectTransportBusy,
  selectTransportPlaying,
  selectTransportRecording,
  type PatternTransportCommand,
} from "../src/state/pattern_transport_state";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";

const status = (overrides: Partial<PatternTransportStatus> = {}): PatternTransportStatus => ({
  engaged: true,
  playing: false,
  recording: false,
  phase: "idle",
  runtimeGeneration: 1,
  transportEpoch: 1,
  originFrame: 0,
  commandId: "command-1",
  publicationPending: false,
  error: null,
  ...overrides,
});

const command = (overrides: Partial<PatternTransportCommand> = {}): PatternTransportCommand => ({
  commandId: "command-1",
  intent: "play_stop",
  epoch: 1,
  expectedRevision: null,
  ...overrides,
});

const engaged = reducePatternTransport(initialPatternTransportState, {
  type: "engaged",
  sessionId: "session-1",
  projectId: "project-1",
  revision: 4,
});

test("a requested command is pending until its own epoch settles", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command(),
  });
  expect(requested.pending).toEqual(command());
  expect(selectTransportBusy(requested)).toBe(true);
  // A second intent while pending is refused locally: the runtime owns the
  // single in-flight operation and the Creator never queues a competitor.
  expect(reducePatternTransport(requested, {
    type: "requested", command: command({commandId: "command-2", epoch: 2}),
  })).toBe(requested);

  // The pending ticket reports the pre-settlement phase; the operation is
  // still pending.
  const submitted = reducePatternTransport(requested, {
    type: "submitted", commandId: "command-1",
    status: status({phase: "awaiting_audio"}),
  });
  expect(submitted.pending).toEqual(command());
  expect(submitted.status?.phase).toBe("awaiting_audio");
  expect(selectTransportBusy(submitted)).toBe(true);

  const settled = reducePatternTransport(submitted, {
    type: "observed", status: status({playing: true}),
  });
  expect(settled.pending).toBeNull();
  expect(selectTransportPlaying(settled)).toBe(true);
  expect(selectTransportBusy(settled)).toBe(false);
});

test("stale observations and foreign tickets are rejected", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command({epoch: 2}),
  });
  const submitted = reducePatternTransport(requested, {
    type: "submitted", commandId: "command-1",
    status: status({phase: "awaiting_audio", transportEpoch: 2}),
  });
  // A ticket for a command this Host never requested cannot move the state.
  expect(reducePatternTransport(submitted, {
    type: "submitted", commandId: "command-foreign",
    status: status({transportEpoch: 3}),
  })).toBe(submitted);
  // An observation from before the pending command is stale.
  expect(reducePatternTransport(submitted, {
    type: "observed", status: status({transportEpoch: 1}),
  })).toBe(submitted);
  // An older runtime generation can never overwrite a newer one.
  const restarted = reducePatternTransport(engaged, {
    type: "observed",
    status: status({runtimeGeneration: 7, transportEpoch: 4, playing: true}),
  });
  expect(reducePatternTransport(restarted, {
    type: "observed",
    status: status({runtimeGeneration: 3, transportEpoch: 9}),
  })).toBe(restarted);
});

test("a failed submit retains the command identity for reconcile-only retry", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command({intent: "record", epoch: 3, expectedRevision: 4}),
  });
  const failed = reducePatternTransport(requested, {
    type: "failed", command: requested.pending!, errorCode: "HOST_TIMEOUT",
  });
  expect(failed.pending).toBeNull();
  expect(failed.lastFailed).toEqual(requested.pending);
  expect(failed.lastCommandId).toBe("command-1");
  expect(failed.errorCode).toBe("HOST_TIMEOUT");

  // Reconcile observes the command actually landed and settled: the retained
  // failure clears without any new intent being issued.
  const reconciled = reducePatternTransport(failed, {
    type: "observed",
    status: status({transportEpoch: 3, recording: true, playing: true}),
  });
  expect(reconciled.lastFailed).toBeNull();
  expect(reconciled.errorCode).toBeNull();
  expect(selectTransportRecording(reconciled)).toBe(true);

  // If instead the command never landed, the identity stays retained.
  const stillUnknown = reducePatternTransport(failed, {
    type: "observed", status: status({transportEpoch: 2}),
  });
  expect(stillUnknown.lastFailed).toEqual(failed.lastFailed);
});

test("an absent or null revision never lowers the retained authoring revision", () => {
  expect(engaged.expectedRevision).toBe(4);
  expect(reducePatternTransport(engaged, {type: "revision", revision: null}))
    .toBe(engaged);
  const advanced = reducePatternTransport(engaged, {type: "revision", revision: 9});
  expect(advanced.expectedRevision).toBe(9);
  expect(reducePatternTransport(advanced, {type: "revision", revision: 6})
    .expectedRevision).toBe(9);
});

test("a retained error phase and publication split are shown honestly", () => {
  const failed = reducePatternTransport(engaged, {
    type: "observed",
    status: status({
      phase: "error",
      error: {code: "IO_ERROR", message: "journal settlement failed", details: {}},
    }),
  });
  expect(failed.errorCode).toBe("IO_ERROR");
  const committedNotPublished = reducePatternTransport(engaged, {
    type: "observed", status: status({publicationPending: true}),
  });
  expect(committedNotPublished.status?.publicationPending).toBe(true);
});

test("losing the engaged session mid-operation retains the failed identity", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command({intent: "record", epoch: 2}),
  });
  const lost = reducePatternTransport(requested, {
    type: "observed", status: status({engaged: false, transportEpoch: 0, commandId: null}),
  });
  expect(lost.pending).toBeNull();
  expect(lost.lastFailed).toEqual(requested.pending);
  expect(lost.errorCode).toBe("HOST_STATE_INVALID");
});

test("an inspection failure surfaces its code without touching identities", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command(),
  });
  const failed = reducePatternTransport(requested, {
    type: "observe-failed", errorCode: "HOST_TIMEOUT",
  });
  expect(failed.errorCode).toBe("HOST_TIMEOUT");
  expect(failed.pending).toEqual(requested.pending);
  expect(failed.lastFailed).toBeNull();
});

test("a new engagement resets every owned identity", () => {
  const requested = reducePatternTransport(engaged, {
    type: "requested", command: command(),
  });
  const reengaged = reducePatternTransport(requested, {
    type: "engaged", sessionId: "session-2", projectId: "project-1", revision: 11,
  });
  expect(reengaged.sessionId).toBe("session-2");
  expect(reengaged.pending).toBeNull();
  expect(reengaged.status).toBeNull();
  expect(reengaged.expectedRevision).toBe(11);
  expect(reducePatternTransport(reengaged, {type: "disengaged"}))
    .toEqual(initialPatternTransportState);
});
