import {describe, expect, test} from "vitest";

import {initialSequenceState, reduceSequence} from "../src/state/sequence_state";
import type {SequenceStatus} from "../src/runtime/runtime_types";

const status = (state: SequenceStatus["state"], overrides: Partial<SequenceStatus> = {}): SequenceStatus => ({
  state,
  sessionId: state === "inactive" ? null : "session-1",
  patternId: "pattern-1",
  pendingPatternId: null,
  expectedRevision: 4,
  nextFlushSequence: 1,
  pendingEventCount: 0,
  effectiveRuntimeFrame: 96_000,
  ...overrides,
});

describe("Sequence state machine", () => {
  test("covers record, next-Bar switch acknowledgement, flush, and stop", () => {
    const recording = reduceSequence(initialSequenceState, {
      type: "recording", status: status("active"), sessionId: "session-1",
    });
    const switching = reduceSequence(recording, {
      type: "switch-pending",
      status: status("switching", {pendingPatternId: "pattern-2"}),
    });
    expect(switching.selectedPatternId).toBe("pattern-1");
    const acknowledged = reduceSequence(switching, {
      type: "boundary", patternId: "pattern-2",
      status: status("active", {patternId: "pattern-2"}),
    });
    expect(acknowledged.selectedPatternId).toBe("pattern-2");
    const flushing = reduceSequence(acknowledged, {type: "flushing", commandId: "command-1"});
    expect(flushing.phase).toBe("flushing");
    expect(reduceSequence(flushing, {
      type: "stopped", commandId: "command-1", status: status("inactive"),
    }).phase).toBe("stopped");
  });

  test("represents recovery and trimming while rejecting impossible transitions", () => {
    const recording = reduceSequence(initialSequenceState, {
      type: "recording", status: status("active"), sessionId: "session-1",
    });
    expect(reduceSequence(recording, {type: "selected", patternId: "pattern-2"}))
      .toBe(recording);
    expect(reduceSequence(initialSequenceState, {type: "flushing", commandId: "bad"}))
      .toBe(initialSequenceState);
    const recovery = reduceSequence(initialSequenceState, {
      type: "recovery",
      candidates: [{sessionId: "session-1", patternId: "pattern-1", bars: 1,
        reason: "interrupted", eventCount: 2}],
    });
    expect(recovery.phase).toBe("recovery");
    const overlay = reduceSequence(initialSequenceState, {type: "trim-overlay"});
    expect(overlay.phase).toBe("trim-overlay");
    expect(reduceSequence(overlay, {type: "trim-closed"}).phase).toBe("stopped");
  });

  test("keeps an active Sequence session beneath the armed-Pad trim overlay", () => {
    const recording = reduceSequence(initialSequenceState, {
      type: "recording", status: status("active"), sessionId: "session-1",
    });
    const overlay = reduceSequence(recording, {type: "trim-overlay"});
    expect(overlay.phase).toBe("trim-overlay");
    expect(overlay.sessionId).toBe("session-1");
    expect(overlay.status?.pendingEventCount).toBe(0);

    const rebased = reduceSequence(overlay, {
      type: "authority", status: status("active", {
        expectedRevision: 5, pendingEventCount: 2,
      }),
    });
    expect(rebased.phase).toBe("trim-overlay");
    expect(rebased.status?.expectedRevision).toBe(5);
    const withoutRecovery = reduceSequence(rebased, {
      type: "recovery", candidates: [],
    });
    expect(withoutRecovery.phase).toBe("trim-overlay");
    expect(reduceSequence(withoutRecovery, {type: "trim-closed"}).phase)
      .toBe("recording");
  });
});
