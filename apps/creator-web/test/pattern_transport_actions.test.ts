import {expect, test, vi} from "vitest";

import {
  inspectPatternTransportJourney,
  isPatternTransportSession,
  observePatternTransportJourney,
  reconcilePatternTransportJourney,
  requestPatternTransportJourney,
} from "../src/runtime/pattern_transport_actions";
import type {CreatorPatternTransportSession} from "../src/runtime/pattern_transport_actions";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {
  initialPatternTransportState,
  reducePatternTransport,
} from "../src/state/pattern_transport_state";

const status: PatternTransportStatus = {
  engaged: true,
  playing: true,
  recording: false,
  phase: "idle",
  runtimeGeneration: 1,
  transportEpoch: 2,
  originFrame: 96_000,
  runtimeFrame: 96_000,
  observedAtMilliseconds: 0,
  commandId: "command-1",
  publicationPending: false,
  currentPatternId: null, pendingSwitch: null,
  error: null,
};

const ticket = {sessionId: "session-1", commandId: "command-1", submit: "accepted" as const, status};

test("transport journeys preserve the exact command identity end to end", async () => {
  const session = {
    requestPatternTransport: vi.fn(async () => ticket),
    inspectPatternTransport: vi.fn(async () => status),
    requestTransportPatternSwitch: vi.fn(async () => ({
      patternId: "00000000-0000-4000-8000-0000000000ee", activationFrame: 96_000,
    })),
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
    requestTransportPatternSwitch: vi.fn(async () => ({
      patternId: "00000000-0000-4000-8000-0000000000ee", activationFrame: 96_000,
    })),
  };
  const retained = {
    sessionId: "session-1",
    projectId: "project-1",
    commandId: "command-1",
    expectedEpoch: 2,
    intent: "record" as const,
    expectedRevision: 7,
  };
  const reconciled = await reconcilePatternTransportJourney(session, retained, engagedState);
  expect(session.requestPatternTransport).toHaveBeenCalledTimes(1);
  expect(session.requestPatternTransport).toHaveBeenCalledWith(retained);
  expect(session.inspectPatternTransport).toHaveBeenCalledWith("session-1");
  expect(reconciled?.ticket.submit).toBe("replayed");
  expect(reconciled?.status).toBe(status);
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
    requestTransportPatternSwitch: async () => ({
      patternId: "00000000-0000-4000-8000-0000000000ee", activationFrame: 96_000,
    }),
  };
  expect(isPatternTransportSession({...session, unrelated: true})).toBe(true);
});

const engagedState = () => reducePatternTransport(initialPatternTransportState, {
  type: "engaged", sessionId: "session-1", projectId: "project-1", revision: 7,
});

test("late inspection cannot resurrect a Stop already settled by the live reducer", async () => {
  const stop = {commandId: "stop", intent: "play_stop" as const, epoch: 3, expectedRevision: null};
  let current = reducePatternTransport(engagedState(), {type: "requested", command: stop});
  const result = Promise.withResolvers<PatternTransportStatus>();
  const session = {
    requestPatternTransport: vi.fn(async () => ticket),
    inspectPatternTransport: vi.fn(() => result.promise),
  };
  const observation = observePatternTransportJourney(session, () => current);
  // Another inspection settles Stop. Pattern selection then legitimately
  // retires that stopped engagement before this older query returns.
  current = reducePatternTransport(current, {
    type: "submitted", commandId: stop.commandId,
    status: {...status, commandId: stop.commandId, transportEpoch: 3, playing: false},
  });
  expect(current.pending).toBeNull();
  result.resolve({...status, engaged: false, commandId: null, transportEpoch: 0, playing: false});
  const after = await observation;
  expect(after?.state.lastFailed).toBeNull();
  expect(session.requestPatternTransport).not.toHaveBeenCalled();
});

test("late inspection of a retired session cannot become a replacement session projection", async () => {
  let current = engagedState();
  const result = Promise.withResolvers<PatternTransportStatus>();
  const session = {requestPatternTransport: async () => ticket, inspectPatternTransport: () => result.promise};
  const observation = observePatternTransportJourney(session, () => current);
  current = reducePatternTransport(current, {
    type: "engaged", sessionId: "session-2", projectId: "project-2", revision: 1,
  });
  result.resolve(status);
  expect(await observation).toBeNull();
});

test("late inspection failure of a replaced session is ignored", async () => {
  let current = engagedState();
  const result = Promise.withResolvers<PatternTransportStatus>();
  const session = {requestPatternTransport: async () => ticket, inspectPatternTransport: () => result.promise};
  const observation = observePatternTransportJourney(session, () => current);
  current = reducePatternTransport(current, {
    type: "engaged", sessionId: "session-2", projectId: "project-2", revision: 1,
  });
  result.reject(Object.assign(new Error("old inspection failed"), {code: "HOST_TIMEOUT"}));
  await expect(observation).resolves.toBeNull();
});

test("a same-session unknown command retains its identity after observation", async () => {
  const command = {commandId: "unknown-record", intent: "record" as const, epoch: 3, expectedRevision: 7};
  const current = reducePatternTransport(engagedState(), {
    type: "failed", command, errorCode: "HOST_TIMEOUT",
  });
  const session = {requestPatternTransport: async () => ticket, inspectPatternTransport: async () => status};
  const after = await observePatternTransportJourney(session, () => current);
  expect(after?.state.lastFailed).toEqual(command);
  expect(after?.state.errorCode).toBe("HOST_TIMEOUT");
});

test("inspection failure of the current session still reaches its caller", async () => {
  const current = engagedState();
  const error = Object.assign(new Error("current inspection failed"), {code: "HOST_TIMEOUT"});
  const session = {
    requestPatternTransport: async () => ticket,
    inspectPatternTransport: async () => { throw error; },
  };
  await expect(observePatternTransportJourney(session, () => current)).rejects.toBe(error);
});

const retryRequest = {
  sessionId: "session-1", projectId: "project-1", commandId: "command-1",
  expectedEpoch: 2, intent: "record" as const, expectedRevision: 7,
};

const replacementState = () => reducePatternTransport(engagedState(), {
  type: "engaged", sessionId: "session-2", projectId: "project-2", revision: 1,
});

test.each(["session", "project", "runtime"] as const)(
  "retry refuses a retained request after its %s owner is replaced", async (owner) => {
    const session = {
      requestPatternTransport: vi.fn(async () => ticket),
      inspectPatternTransport: vi.fn(async () => status),
    };
    const current = owner === "runtime" ? initialPatternTransportState : {
      ...engagedState(),
      ...(owner === "session" ? {sessionId: "session-2"} : {projectId: "project-2"}),
    };
    expect(await reconcilePatternTransportJourney(session, retryRequest, () => current)).toBeNull();
    expect(session.requestPatternTransport).not.toHaveBeenCalled();
  },
);

test("retry does not inspect a retired owner after its late submission returns", async () => {
  let current = engagedState();
  const submitted = Promise.withResolvers<typeof ticket>();
  const session = {
    requestPatternTransport: vi.fn(() => submitted.promise),
    inspectPatternTransport: vi.fn(async () => status),
  };
  const retry = reconcilePatternTransportJourney(session, retryRequest, () => current);
  current = replacementState();
  submitted.resolve(ticket);
  expect(await retry).toBeNull();
  expect(session.inspectPatternTransport).not.toHaveBeenCalled();
});

test("retry discards inspection returned after its owner was replaced", async () => {
  let current = engagedState();
  const inspected = Promise.withResolvers<PatternTransportStatus>();
  const inspecting = Promise.withResolvers<void>();
  const session = {
    requestPatternTransport: vi.fn(async () => ticket),
    inspectPatternTransport: vi.fn(() => {
      inspecting.resolve();
      return inspected.promise;
    }),
  };
  const retry = reconcilePatternTransportJourney(session, retryRequest, () => current);
  await inspecting.promise;
  current = replacementState();
  inspected.resolve(status);
  expect(await retry).toBeNull();
});

test.each(["submission", "inspection"] as const)(
  "retry ignores a replaced owner's late %s failure", async (leg) => {
    let current = engagedState();
    const pending = Promise.withResolvers<never>();
    const started = Promise.withResolvers<void>();
    const fail = () => { started.resolve(); return pending.promise; };
    const session = {
      requestPatternTransport: leg === "submission" ? fail : async () => ticket,
      inspectPatternTransport: leg === "inspection" ? fail : async () => status,
    };
    const retry = reconcilePatternTransportJourney(session, retryRequest, () => current);
    await started.promise;
    current = replacementState();
    pending.reject(Object.assign(new Error("old retry failed"), {code: "HOST_TIMEOUT"}));
    await expect(retry).resolves.toBeNull();
  },
);

test.each(["submission", "inspection"] as const)(
  "retry preserves the current owner's %s failure", async (leg) => {
    const error = Object.assign(new Error("current retry failed"), {code: "HOST_TIMEOUT"});
    const fail = async () => { throw error; };
    const session = {
      requestPatternTransport: leg === "submission" ? fail : async () => ticket,
      inspectPatternTransport: leg === "inspection" ? fail : async () => status,
    };
    await expect(reconcilePatternTransportJourney(session, retryRequest, engagedState)).rejects.toBe(error);
  },
);
