import {afterEach, expect, test, vi} from "vitest";
import type {
  PatternCountInReceipt,
  PatternCountInRequest,
  PatternCountInStatus,
  PatternCountInTicket,
  PatternTransportStatus,
} from "@lmdj/web-runtime-platform/runtime_types";
import {
  countInBeatsRemaining,
  countInLocksPatternSelection,
  initialCountInState,
  type CountInState,
  createCountInController,
  isCountInSession,
  type CountInController,
} from "../src/runtime/count_in_controller";

const controllers: CountInController[] = [];
afterEach(() => {
  for (const controller of controllers.splice(0)) controller.dispose();
  vi.useRealTimers();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}

function fixture() {
  const capability = {supported: true, negotiated: true, outputReady: true,
    runtimeGeneration: "9007199254740993", frameEpoch: "9007199254740995",
    nextSerial: "9007199254740997", inputCapacity: 64};
  const ordinary = {engaged: false, phase: "idle", playing: false,
    recording: false, runtimeGeneration: 1, transportEpoch: 0, originFrame: 0,
    runtimeFrame: 0, observedAtMilliseconds: 0, commandId: null,
    publicationPending: false, currentPatternId: null, pendingSwitch: null, error: null} satisfies PatternTransportStatus;
  let request: PatternCountInRequest | null = null;
  let status: PatternCountInStatus | null = null;
  let metronome = false;
  const ticket = (): PatternCountInTicket => {
    if (request === null) throw new Error("test has no original request");
    return {sessionId: request.sessionId, commandId: request.commandId,
      runtimeGeneration: request.runtimeGeneration, frameEpoch: request.frameEpoch,
      scheduleSerial: request.scheduleSerial};
  };
  const receipt = (result: PatternCountInReceipt["result"], cancelled = false): PatternCountInReceipt => ({
    runtimeGeneration: capability.runtimeGeneration, frameEpoch: capability.frameEpoch,
    scheduleSerial: capability.nextSerial, transportEpoch: cancelled ? "2" : "1",
    patternGeneration: "3", patternId: "pattern", result,
    effectiveFrame: result === "applied" ? (cancelled ? 110000 : 100000) : null,
    originFrame: result === "applied" ? 100000 : null,
    playing: result === "applied" && !cancelled,
  });
  const session = {
    diagnostics: vi.fn(() => ({state: "running"})),
    queryPatternCountInCapabilities: vi.fn(async () => capability),
    setCountInMetronome: vi.fn((_enabled: boolean) => {}),
    inspectPatternTransport: vi.fn(async (_sessionId: string): Promise<PatternTransportStatus> => ordinary),
    requestPatternCountIn: vi.fn(async (value: PatternCountInRequest) => {
      request = value;
      status = {ticket: ticket(), countIn: {...ticket(), phase: "armed", bars: value.bars,
        bpm: 120, barFrames: 96000, countInFrame: 4000,
        startFrame: 4000 + 96000 * value.bars}, startReceipt: null, cancelReceipt: null,
        openingPending: false, openingComplete: false, observedAtMilliseconds: 0, error: null};
      return {submit: "accepted" as const, ticket: ticket(), status};
    }),
    inspectPatternCountIn: vi.fn(async (_ticket: PatternCountInTicket, _consume = false) => {
      if (status === null) throw new Error("no test status");
      return status;
    }),
    cancelPatternCountIn: vi.fn(async (_cancel: Parameters<
      import("../src/runtime/count_in_controller").CreatorCountInSession["cancelPatternCountIn"]>[0]) => {
      if (status === null) throw new Error("no test status");
      return {submit: "accepted" as const, ticket: ticket(), status};
    }),
  };
  const onTransport = vi.fn();
  const onError = vi.fn();
  const controller = createCountInController({session, sessionId: "session", projectId: "project",
    metronomeEnabled: () => metronome, onTransport, onError});
  controllers.push(controller);
  return {session, controller, capability, ordinary, ticket, receipt, onTransport, onError,
    get status() {return status!;},
    set status(value: PatternCountInStatus) {status = value;},
    set metronome(value: boolean) {metronome = value;},
  };
}

test("legacy or incomplete sessions are not advertised as a count-in capability", () => {
  expect(isCountInSession(null)).toBe(false);
  expect(isCountInSession({requestPatternTransport() {}})).toBe(false);
  const f = fixture();
  expect(isCountInSession(f.session)).toBe(true);
  expect(isCountInSession({...f.session, setCountInMetronome: undefined})).toBe(false);
});

test.each(["supported", "negotiated", "outputReady"] as const)(
  "unavailable %s refuses the schedule without an ordinary Record fallback", async (field) => {
    const f = fixture();
    f.capability[field] = false;
    await f.controller.start(2, 7);
    expect(f.controller.getState()).toMatchObject({active: false, errorCode: "UNSUPPORTED_AUDIO"});
    expect(f.session.requestPatternCountIn).not.toHaveBeenCalled();
    expect(f.session.setCountInMetronome).not.toHaveBeenCalled();
    expect(f.onError).toHaveBeenCalledOnce();
  },
);

test("admission preserves exact decimal identities and current committed revision", async () => {
  const f = fixture();
  f.ordinary.transportEpoch = Number.MAX_SAFE_INTEGER;
  await f.controller.start(2, 17);
  expect(f.session.requestPatternCountIn).toHaveBeenCalledWith(expect.objectContaining({
    sessionId: "session", projectId: "project", bars: 2, expectedRevision: 17,
    runtimeGeneration: "9007199254740993", frameEpoch: "9007199254740995",
    scheduleSerial: "9007199254740997", expectedEpoch: "9007199254740992",
  }));
  expect(f.controller.getState().ticket).toEqual(f.ticket());
});

test("a second start cannot pass an awaiting capability owner", async () => {
  const f = fixture();
  const capability = deferred<typeof f.capability>();
  f.session.queryPatternCountInCapabilities.mockReturnValue(capability.promise);
  const start = f.controller.start(1, 4);
  expect(f.controller.getState().active).toBe(true);
  await f.controller.start(2, 5);
  expect(f.session.queryPatternCountInCapabilities).toHaveBeenCalledOnce();
  capability.resolve(f.capability);
  await start;
  expect(f.session.requestPatternCountIn).toHaveBeenCalledOnce();
  expect(f.session.requestPatternCountIn.mock.calls[0]![0].bars).toBe(1);
});

test("Record before admission returns retains one actual cancellation", async () => {
  const f = fixture();
  const capability = deferred<typeof f.capability>();
  f.session.queryPatternCountInCapabilities.mockReturnValue(capability.promise);
  const start = f.controller.start(1, 4);
  await f.controller.cancel("record");
  expect(f.controller.getState()).toMatchObject({active: true, phase: "cancelling"});
  expect(f.session.cancelPatternCountIn).not.toHaveBeenCalled();
  capability.resolve(f.capability);
  await start;
  expect(f.session.cancelPatternCountIn).toHaveBeenCalledOnce();
  expect(f.session.cancelPatternCountIn).toHaveBeenCalledWith(expect.objectContaining({
    ticket: f.ticket(), expectedEpoch: "2", intent: "record",
  }));
  expect(f.controller.getState().active).toBe(true);
});

test("planned S and opening completion are not substituted for an Applied receipt", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  expect(countInBeatsRemaining(f.status, 100001)).toBe(0);
  expect(f.controller.getState()).toMatchObject({phase: "counting", recording: false});
  f.status = {...f.status, startReceipt: f.receipt("applied"), openingPending: true};
  await f.controller.observe();
  expect(f.controller.getState()).toMatchObject({phase: "recording", recording: true,
    nativeDownbeatFrame: 100000, active: true});
  expect(f.session.inspectPatternCountIn.mock.calls.some(([, consume]) => consume)).toBe(false);
});

test("cancellation admission does not unlock; exact terminal consumption does", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  await f.controller.cancel("play_stop");
  expect(f.controller.getState()).toMatchObject({phase: "cancelling", active: true});
  expect(f.session.inspectPatternCountIn.mock.calls.some(([, consume]) => consume)).toBe(false);
  f.status = {...f.status, startReceipt: f.receipt("cancelled"),
    cancelReceipt: f.receipt("cancelled", true)};
  await f.controller.observe();
  expect(f.controller.getState()).toMatchObject({active: false, recording: false, phase: "idle"});
  expect(f.session.inspectPatternCountIn.mock.calls.filter(([, consume]) => consume)).toHaveLength(1);
});

test("a physically pending consumer keeps the cancellation lock through the real release", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  f.status = {...f.status, startReceipt: f.receipt("cancelled"), cancelReceipt: f.receipt("cancelled", true)};
  const inspect = f.session.inspectPatternCountIn.getMockImplementation()!;
  let released = false;
  f.session.inspectPatternCountIn.mockImplementation(async (ticket, consume) => {
    if (consume && !released) throw Object.assign(new Error("input release pending"), {code: "HOST_STATE_INVALID"});
    return inspect(ticket, consume);
  });
  await f.controller.observe();
  expect(f.controller.getState().active).toBe(true);
  expect(f.onError).not.toHaveBeenCalled();
  released = true;
  await f.controller.observe();
  expect(f.controller.getState().active).toBe(false);
});

test.each(["refused-cutoff", "missing-cutoff", "missing-start"] as const)(
  "terminal %s keeps physical debt until the actual failed-owner consume ACK", async (shape) => {
    const f = fixture();
    await f.controller.start(1, 4);
    f.status = {...f.status, startReceipt: shape === "missing-start" ? null : f.receipt("applied"),
      cancelReceipt: shape === "refused-cutoff" ? f.receipt("refused", true) : null,
      openingPending: false, openingComplete: shape !== "missing-start",
      error: {code: "IO_ERROR", message: "original durable owner failed", details: {}}};
    const inspect = f.session.inspectPatternCountIn.getMockImplementation()!;
    let physicalAck = false;
    f.session.inspectPatternCountIn.mockImplementation(async (ticket, consume) => {
      if (consume && !physicalAck) throw Object.assign(new Error("physical owner pending"), {code: "HOST_STATE_INVALID"});
      return inspect(ticket, consume);
    });
    await f.controller.observe();
    expect(f.session.inspectPatternCountIn.mock.calls.filter(([, consume]) => consume)).toHaveLength(1);
    expect(f.controller.getState().active).toBe(true);
    physicalAck = true;
    f.session.inspectPatternTransport.mockRejectedValue(Object.assign(new Error("ordinary session closed"), {code: "HOST_STATE_INVALID"}));
    await f.controller.observe();
    expect(f.controller.getState()).toMatchObject({active: false, errorCode: "IO_ERROR"});
    expect(f.session.inspectPatternCountIn.mock.calls.filter(([, consume]) => consume)).toHaveLength(2);
  },
);

test("an unrelated held ordinary query cannot prevent original count-in consumption", async () => {
  const f = fixture();
  const projection = deferred<typeof f.ordinary>();
  f.session.inspectPatternTransport.mockResolvedValueOnce(f.ordinary).mockReturnValue(projection.promise);
  const start = f.controller.start(1, 4);
  // Only microtasks are advanced. No lifecycle timeout is the release proof.
  for (let turn = 0; turn < 30; turn++) await Promise.resolve();
  expect(f.session.requestPatternCountIn).toHaveBeenCalledOnce();
  f.status = {...f.status, startReceipt: f.receipt("cancelled"), cancelReceipt: f.receipt("cancelled", true)};
  const observed = f.controller.observe();
  try {
    for (let turn = 0; turn < 30; turn++) await Promise.resolve();
    expect(f.session.inspectPatternCountIn.mock.calls.filter(([, consume]) => consume)).toHaveLength(1);
    expect(f.controller.getState().active, "final projection still gates usable ordinary transport").toBe(true);
  } finally {
    projection.resolve({...f.ordinary, transportEpoch: 2});
    await start;
    await observed;
  }
  expect(f.controller.getState().active).toBe(false);
});

test("a lost cancellation reply is retried only by the user's same original identity", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  f.session.cancelPatternCountIn.mockRejectedValueOnce(Object.assign(new Error("reply lost"), {code: "HOST_TIMEOUT"}));
  await f.controller.cancel("record");
  await f.controller.observe();
  expect(f.controller.getState().active).toBe(true);
  expect(f.session.cancelPatternCountIn).toHaveBeenCalledOnce();
  await f.controller.cancel("play_stop");
  expect(f.session.cancelPatternCountIn.mock.calls[1]![0]).toEqual(f.session.cancelPatternCountIn.mock.calls[0]![0]);
});

test("Record-off waits for opening/closure and preserves Native's S for the JS handoff", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  f.status = {...f.status, startReceipt: f.receipt("applied"), openingPending: true};
  await f.controller.observe();
  await f.controller.cancel("record");
  f.status = {...f.status, cancelReceipt: {...f.receipt("applied", true), playing: true}};
  await f.controller.observe();
  expect(f.controller.getState().active).toBe(true);
  f.status = {...f.status, openingPending: false, openingComplete: true};
  await f.controller.observe();
  expect(f.controller.getState()).toMatchObject({active: false, recording: false, nativeDownbeatFrame: 100000});
});

test("a positive consume is not retried when the following ordinary inspection fails", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  f.status = {...f.status, startReceipt: f.receipt("cancelled"), cancelReceipt: f.receipt("cancelled", true)};
  // The positive consume occurs before its following ordinary projection.
  const unavailable = new Error("ordinary projection unavailable");
  f.session.inspectPatternTransport.mockRejectedValueOnce(unavailable);
  await f.controller.observe();
  expect(f.controller.getState().active).toBe(false);
  expect(f.onError).toHaveBeenCalledWith(unavailable);
  await f.controller.observe();
  expect(f.session.inspectPatternCountIn.mock.calls.filter(([, consume]) => consume)).toHaveLength(1);
});

test.each(["running", "restart-required"])("SDK %s distinguishes a known refusal from unknown caller debt", async (sdkState) => {
  const f = fixture();
  f.session.diagnostics.mockReturnValue({state: sdkState});
  f.session.requestPatternCountIn.mockRejectedValue(Object.assign(new Error("request refused or unknown"), {code: "HOST_TIMEOUT"}));
  await f.controller.start(1, 4);
  expect(f.controller.getState().active).toBe(sdkState !== "running");
  expect(f.controller.getState().ticket === null).toBe(sdkState === "running");
});

test("a foreign admission never releases the original caller or consumes another ticket", async () => {
  const f = fixture();
  const request = f.session.requestPatternCountIn.getMockImplementation()!;
  f.session.requestPatternCountIn.mockImplementation(async (value) => {
    const result = await request(value);
    return {...result, ticket: {...result.ticket, scheduleSerial: "18"}};
  });
  await f.controller.start(1, 4);
  expect(f.controller.getState()).toMatchObject({active: true, errorCode: "HOST_PROTOCOL_MISMATCH"});
  expect(f.controller.getState().ticket).toEqual(f.ticket());
  expect(f.session.inspectPatternCountIn.mock.calls.some(([, consume]) => consume)).toBe(false);
});

test("a late observation cannot publish into a retired Project owner", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  const held = deferred<PatternCountInStatus>();
  f.session.inspectPatternCountIn.mockReturnValueOnce(held.promise);
  const observation = f.controller.observe();
  f.controller.dispose();
  const previous = f.controller.getState();
  const transportCalls = f.onTransport.mock.calls.length;
  held.resolve({...f.status, startReceipt: f.receipt("applied"), openingPending: true});
  await observation;
  expect(f.controller.getState()).toBe(previous);
  expect(f.onTransport).toHaveBeenCalledTimes(transportCalls);
  expect(f.session.inspectPatternCountIn.mock.calls.some(([, consume]) => consume)).toBe(false);
});

test("the polling timer cannot overlap an outstanding observation", async () => {
  vi.useFakeTimers();
  const f = fixture();
  await f.controller.start(1, 4);
  const held = deferred<PatternCountInStatus>();
  f.session.inspectPatternCountIn.mockReturnValueOnce(held.promise);
  const observation = f.controller.observe();
  const calls = f.session.inspectPatternCountIn.mock.calls.length;
  await vi.advanceTimersByTimeAsync(1000);
  await f.controller.observe();
  expect(f.session.inspectPatternCountIn).toHaveBeenCalledTimes(calls);
  held.resolve(f.status);
  await observation;
  await vi.advanceTimersByTimeAsync(250);
  expect(f.session.inspectPatternCountIn).toHaveBeenCalledTimes(calls + 1);
});

test("a pending admission cannot queue the native metronome toggle behind itself", async () => {
  const f = fixture();
  const held = deferred<Awaited<ReturnType<typeof f.session.requestPatternCountIn>>>();
  const request = f.session.requestPatternCountIn.getMockImplementation()!;
  f.session.requestPatternCountIn.mockImplementation(async (value) => {
    await request(value);
    return held.promise;
  });
  const start = f.controller.start(1, 4);
  await vi.waitFor(() => expect(f.session.requestPatternCountIn).toHaveBeenCalledOnce());
  f.controller.setMetronome(true);
  expect(f.session.setCountInMetronome).toHaveBeenLastCalledWith(true);
  held.resolve({submit: "accepted", ticket: f.ticket(), status: f.status});
  await start;
});

test("late capability reads use the current metronome preference", async () => {
  const f = fixture();
  const held = deferred<typeof f.capability>();
  f.session.queryPatternCountInCapabilities.mockReturnValue(held.promise);
  const start = f.controller.start(1, 4);
  f.metronome = true;
  held.resolve(f.capability);
  await start;
  expect(f.session.setCountInMetronome).toHaveBeenCalledWith(true);
});

test("countdown follows each real rounded-Bar marker without declaring recording at S", async () => {
  const f = fixture();
  await f.controller.start(2, 4);
  f.status = {...f.status, countIn: {...f.status.countIn!, bpm: 129, barFrames: 89303,
    countInFrame: 4000, startFrame: 182606}};
  expect(countInBeatsRemaining(f.status, 3999)).toBe(8);
  expect(countInBeatsRemaining(f.status, 4001)).toBe(8);
  // 22,325 * 129 = 2,879,925 < 2,880,000; the next frame owns beat 1.
  expect(countInBeatsRemaining(f.status, 4000 + 22325)).toBe(8);
  expect(countInBeatsRemaining(f.status, 4000 + 22326)).toBe(7);
  expect(countInBeatsRemaining(f.status, 93303)).toBe(4);
  expect(countInBeatsRemaining(f.status, 182606)).toBe(0);
  expect(countInBeatsRemaining(null, 0)).toBeNull();
});

test("127 BPM countdown follows Native's actual cue at 23677, not the ordinary beat at 23678", async () => {
  const f = fixture();
  await f.controller.start(1, 4);
  f.status = {...f.status, countIn: {...f.status.countIn!, bpm: 127, bars: 1,
    barFrames: 90709, countInFrame: 1000, startFrame: 91709}};
  // Native divides its rounded 90,709-frame Bar: nearest quarter is 22,677.
  // The ordinary PPQ ceiling is 22,678; a UI sharing that grid is one frame late.
  expect(countInBeatsRemaining(f.status, 23676)).toBe(4);
  expect(countInBeatsRemaining(f.status, 23677)).toBe(3);
});

test("Pattern selection waits for durable opening while retaining the original COUNT-IN caller", async () => {
  const f = fixture();
  expect(countInLocksPatternSelection(f.controller.getState())).toBe(false);
  await f.controller.start(1, 4);
  const original = structuredClone(f.controller.getState().ticket);
  expect(countInLocksPatternSelection(f.controller.getState())).toBe(true);
  f.status = {...f.status, startReceipt: f.receipt("applied"), openingPending: true};
  await f.controller.observe();
  expect(f.controller.getState().recording).toBe(true);
  expect(countInLocksPatternSelection(f.controller.getState())).toBe(true);
  f.status = {...f.status, openingPending: false, openingComplete: true};
  await f.controller.observe();
  expect(countInLocksPatternSelection(f.controller.getState())).toBe(false);
  expect(f.controller.getState()).toMatchObject({active: true, phase: "recording",
    ticket: original, nativeDownbeatFrame: 100000});
  expect(f.session.inspectPatternCountIn.mock.calls.some(([, consume]) => consume)).toBe(false);
  await f.controller.cancel("record");
  expect(countInLocksPatternSelection(f.controller.getState())).toBe(true);
  expect(f.controller.getState().ticket).toEqual(original);
});

test.each([
  {phase: "preparing"}, {phase: "counting"}, {phase: "cancelling"}, {phase: "settling"},
  {recording: false}, {errorCode: "IO_ERROR"}, {status: null},
] satisfies Partial<CountInState>[])("Pattern selection stays closed for retained $phase $recording $errorCode $status", async (change) => {
  const f = fixture();
  await f.controller.start(1, 4);
  const ready: CountInState = {...initialCountInState, active: true, phase: "recording", recording: true,
    ticket: f.ticket(), status: {...f.status, openingComplete: true,
      startReceipt: f.receipt("applied")}};
  expect(countInLocksPatternSelection(ready)).toBe(false);
  expect(countInLocksPatternSelection({...ready, ...change})).toBe(true);
});

test.each(["openingPending", "openingIncomplete", "noReceipt", "refused", "cancelled", "error"] as const)(
  "Pattern selection rejects $0 even when the COUNT-IN lamp says recording", async (condition) => {
    const f = fixture(); await f.controller.start(1, 4);
    const status: PatternCountInStatus = {...f.status, startReceipt: f.receipt("applied"), openingComplete: true};
    if (condition === "openingPending") Object.assign(status, {openingPending: true});
    if (condition === "openingIncomplete") Object.assign(status, {openingComplete: false});
    if (condition === "noReceipt") Object.assign(status, {startReceipt: null});
    if (condition === "refused") Object.assign(status, {startReceipt: f.receipt("refused")});
    if (condition === "cancelled") Object.assign(status, {cancelReceipt: f.receipt("applied", true)});
    if (condition === "error") Object.assign(status, {error: {code: "IO_ERROR", message: "held failure", retryable: false}});
    expect(countInLocksPatternSelection({...initialCountInState, active: true, phase: "recording",
      recording: true, status})).toBe(true);
  },
);

test("a consumed COUNT-IN caller waiting for its final projection cannot replay cancellation", async () => {
  const f = fixture();
  let consumed = false;
  const projection = deferred<PatternTransportStatus>();
  f.session.inspectPatternCountIn.mockImplementation(async (_ticket, consume = false) => {
    if (consume) consumed = true;
    return f.status;
  });
  f.session.inspectPatternTransport.mockImplementation(async () => consumed ? projection.promise : f.ordinary);
  await f.controller.start(1, 4);
  f.status = {...f.status, startReceipt: f.receipt("applied"), openingComplete: true};
  await f.controller.observe();
  await f.controller.cancel("record");
  f.status = {...f.status, cancelReceipt: f.receipt("applied", true)};
  const finishing = f.controller.observe();
  await vi.waitFor(() => expect(consumed).toBe(true));
  expect(f.controller.getState()).toMatchObject({active: true, phase: "settling"});
  try {
    await f.controller.cancel("play_stop");
    expect(f.session.cancelPatternCountIn).toHaveBeenCalledOnce();
    expect(f.controller.getState().phase).toBe("settling");
  } finally {
    projection.resolve({...f.ordinary, engaged: true, playing: true, recording: false,
      transportEpoch: 2, currentPatternId: "terminal-pattern"});
    await finishing;
  }
  expect(f.controller.getState()).toMatchObject({active: false, phase: "idle"});
});
