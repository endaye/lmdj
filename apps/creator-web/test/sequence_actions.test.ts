import {expect, test, vi} from "vitest";

import {
  beginSequenceJourney,
  disarmSequenceCaptureJourney,
  editPatternEventsJourney,
  isSequenceSession,
  reconcileSequenceAuthoringRevision,
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
    disarmSequenceCapture: vi.fn(async () => true),
  } as unknown as CreatorSequenceRuntimeSession;
  await beginSequenceJourney(session, {
    sessionId: "session-1", patternId: "pattern-1", expectedRevision: 3,
  });
  await stopSequenceJourney(session, "session-1", "command-1");
  await disarmSequenceCaptureJourney(session, "session-1", 17);
  await refreshSequenceJourney(session, "project-1");
  expect(session.beginSequence).toHaveBeenCalledWith({
    sessionId: "session-1", patternId: "pattern-1", expectedRevision: 3,
  });
  expect(session.stopSequence).toHaveBeenCalledWith({
    sessionId: "session-1", commandId: "command-1",
  });
  expect(session.disarmSequenceCapture).toHaveBeenCalledWith({
    sessionId: "session-1", slot: 17,
  });
  expect(session.querySequenceStatus).toHaveBeenCalledWith("project-1");
  expect(session.listSequenceRecovery).toHaveBeenCalledWith("project-1");
});

test("Sequence capability detection includes settings and Pattern authoring", () => {
  const value = Object.fromEntries([
    "beginSequence", "flushSequence", "createPattern", "updateSequenceSettings", "stopSequence",
    "editPatternEvents", "disarmSequenceCapture",
    "requestPatternSwitch", "querySequenceStatus", "listSequenceRecovery",
    "applySequenceRecovery", "discardSequenceRecovery", "subscribeSequenceBarBoundary",
  ].map((name) => [name, () => {}]));
  expect(isSequenceSession(value)).toBe(true);
  expect(isSequenceSession({...value, flushSequence: undefined})).toBe(false);
  expect(isSequenceSession({...value, updateSequenceSettings: undefined})).toBe(false);
  expect(isSequenceSession({...value, editPatternEvents: undefined})).toBe(false);
  expect(isSequenceSession({...value, createPattern: undefined})).toBe(false);
  expect(isSequenceSession({...value, applySequenceRecovery: undefined})).toBe(false);
  expect(isSequenceSession({...value, discardSequenceRecovery: undefined})).toBe(false);
});

test("the Pattern events edit journey delegates one gesture's command verbatim", async () => {
  const result = {
    patternId: "pattern-1",
    committedRevision: 5,
    replayed: false,
    projectRevision: 5,
    publication: "live" as const,
    patternPublication: {generation: 7, activationFrame: 192_000},
    snapshotError: null,
  };
  const session = {
    editPatternEvents: vi.fn(async () => result),
  } as unknown as CreatorSequenceRuntimeSession;
  const request = {
    patternId: "pattern-1",
    expectedRevision: 4,
    remove: [{slot: 1, onsetTick: 240}],
    put: [{slot: 1, onsetTick: 480, durationTick: 240, velocity: 100}],
  };
  await expect(editPatternEventsJourney(session, request)).resolves.toBe(result);
  expect(session.editPatternEvents).toHaveBeenCalledWith(request);
});

test("a stale journal refresh cannot lower the committed authoring revision", () => {
  expect(reconcileSequenceAuthoringRevision(70, 70, 66)).toBe(70);
});
