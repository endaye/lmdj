import {expect, test, vi} from "vitest";

import {
  inspectPatternTransportJourney,
  isPatternTransportSession,
  reconcilePatternTransportJourney,
  requestPatternTransportJourney,
} from "../src/runtime/pattern_transport_actions";
import type {CreatorPatternTransportSession} from "../src/runtime/pattern_transport_actions";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";

const status: PatternTransportStatus = {
  engaged: true,
  playing: true,
  recording: false,
  phase: "idle",
  runtimeGeneration: 1,
  transportEpoch: 2,
  originFrame: 96_000,
  commandId: "command-1",
  publicationPending: false,
  error: null,
};

const ticket = {sessionId: "session-1", commandId: "command-1", submit: "accepted" as const, status};

test("transport journeys preserve the exact command identity end to end", async () => {
  const session = {
    requestPatternTransport: vi.fn(async () => ticket),
    inspectPatternTransport: vi.fn(async () => status),
  };
  const request = {
    sessionId: "session-1",
    projectId: "project-1",
    commandId: "command-1",
    expectedEpoch: 2,
    intent: "record" as const,
    expectedRevision: 7,
  };
  await requestPatternTransportJourney(session, request);
  expect(session.requestPatternTransport).toHaveBeenCalledWith(request);
  await inspectPatternTransportJourney(session, "session-1");
  expect(session.inspectPatternTransport).toHaveBeenCalledWith("session-1");
});

test("retry resends the retained command verbatim and re-inspects; it never issues an inverse toggle", async () => {
  const session = {
    requestPatternTransport: vi.fn(async () => ({...ticket, submit: "replayed" as const})),
    inspectPatternTransport: vi.fn(async () => status),
  };
  const retained = {
    sessionId: "session-1",
    projectId: "project-1",
    commandId: "command-1",
    expectedEpoch: 2,
    intent: "record" as const,
    expectedRevision: 7,
  };
  const reconciled = await reconcilePatternTransportJourney(session, retained);
  expect(session.requestPatternTransport).toHaveBeenCalledTimes(1);
  expect(session.requestPatternTransport).toHaveBeenCalledWith(retained);
  expect(session.inspectPatternTransport).toHaveBeenCalledWith("session-1");
  expect(reconciled.ticket.submit).toBe("replayed");
  expect(reconciled.status).toBe(status);
});

test("transport capability detection requires both request and inspect", () => {
  const value = {
    requestPatternTransport: () => {},
    inspectPatternTransport: () => {},
  };
  expect(isPatternTransportSession(value)).toBe(true);
  expect(isPatternTransportSession({requestPatternTransport: value.requestPatternTransport}))
    .toBe(false);
  expect(isPatternTransportSession(null)).toBe(false);
  expect(isPatternTransportSession(undefined)).toBe(false);
  expect(isPatternTransportSession({...value, inspectPatternTransport: 1})).toBe(false);
});

test("the capability surface is structural: extra members do not matter", () => {
  const session: CreatorPatternTransportSession = {
    requestPatternTransport: async () => ticket,
    inspectPatternTransport: async () => status,
  };
  expect(isPatternTransportSession({...session, unrelated: true})).toBe(true);
});
