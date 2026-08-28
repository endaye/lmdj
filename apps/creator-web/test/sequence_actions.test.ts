import {expect, test, vi} from "vitest";

import {
  beginSequenceJourney,
  isSequenceSession,
  refreshSequenceJourney,
  stopSequenceJourney,
} from "../src/runtime/sequence_actions";
import type {CreatorSequenceRuntimeSession, SequenceStatus} from "../src/runtime/runtime_types";

const status: SequenceStatus = {
  state: "active", sessionId: "session-1", patternId: "pattern-1",
  pendingPatternId: null, expectedRevision: 3, nextFlushSequence: 1,
  pendingEventCount: 2, effectiveRuntimeFrame: 96_000,
};

test("Sequence journeys preserve typed command identities and query both authorities", async () => {
  const session = {
    beginSequence: vi.fn(async () => ({...status, committedRevision: null,
      replayed: false, projectRevision: 3})),
    stopSequence: vi.fn(async () => ({...status, state: "inactive" as const,
      committedRevision: 4, replayed: false, projectRevision: 4})),
    querySequenceStatus: vi.fn(async () => status),
    listSequenceRecovery: vi.fn(async () => []),
  } as unknown as CreatorSequenceRuntimeSession;
  await beginSequenceJourney(session, {
    sessionId: "session-1", patternId: "pattern-1", expectedRevision: 3,
  });
  await stopSequenceJourney(session, "session-1", "command-1");
  await refreshSequenceJourney(session, "project-1");
  expect(session.beginSequence).toHaveBeenCalledWith({
    sessionId: "session-1", patternId: "pattern-1", expectedRevision: 3,
  });
  expect(session.stopSequence).toHaveBeenCalledWith({
    sessionId: "session-1", commandId: "command-1",
  });
  expect(session.querySequenceStatus).toHaveBeenCalledWith("project-1");
  expect(session.listSequenceRecovery).toHaveBeenCalledWith("project-1");
});

test("Sequence capability detection includes settings and Pattern authoring", () => {
  const value = Object.fromEntries([
    "beginSequence", "flushSequence", "createPattern", "updateSequenceSettings", "stopSequence",
    "requestPatternSwitch", "querySequenceStatus", "listSequenceRecovery",
    "applySequenceRecovery", "discardSequenceRecovery", "subscribeSequenceBarBoundary",
  ].map((name) => [name, () => {}]));
  expect(isSequenceSession(value)).toBe(true);
  expect(isSequenceSession({...value, flushSequence: undefined})).toBe(false);
  expect(isSequenceSession({...value, updateSequenceSettings: undefined})).toBe(false);
});
