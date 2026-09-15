import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {PerformSurface} from "../src/components/perform_surface";
import type {CreatorPerformanceRuntimeSession} from "../src/runtime/runtime_types";
import {
  createPerformController,
  type PerformControllerDependencies,
} from "../src/state/perform_state";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";

const ids = {
  project: "11111111-1111-4111-8111-111111111111",
  pattern1: "22222222-2222-4222-8222-222222222222",
  pattern2: "33333333-3333-4333-8333-333333333333",
  session: "44444444-4444-4444-8444-444444444444",
  performance: "55555555-5555-4555-8555-555555555555",
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

const project = {
  projectId: ids.project,
  patternId: ids.pattern1,
  revision: 7,
  bpm: 120,
  assetCount: 16,
  assignedPadCount: 16,
  bundleDigest: "a".repeat(64),
  key: "—" as const,
  pads: Array.from({length: 64}, (_, slot) => ({
    slot,
    assetId: slot < 16
      ? `${String(slot + 1).padStart(8, "0")}-1111-4111-8111-111111111111`
      : null,
  })),
  patterns: [
    {patternId: ids.pattern1, bars: 1 as const},
    {patternId: ids.pattern2, bars: 4 as const},
  ],
  patternSlots: [ids.pattern1, ids.pattern2, ...Array<string | null>(14).fill(null)],
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};

function creatorState(overrides: Partial<CreatorState> = {}): CreatorState {
  return {
    ...initialCreatorState,
    project: {phase: "ready", projects: [], current: project},
    runtime: {phase: "ready", errorCode: null, errorDetails: {}},
    audio: {phase: "running"},
    ...overrides,
  };
}

function status(state: "unconfigured" | "configured" | "ready" | "unavailable") {
  const config = state === "unconfigured" ? null : {
    performRecordingFrames: 86_400_000,
    performRecordingQueueBatches: 32,
  };
  return state === "unavailable" ? {
    state,
    config,
    error: {code: "tap-initialization-failed" as const,
      message: "Reload after checking the audio processor URL."},
  } : {state, config, error: null};
}

function sessionFixture(initialStatus = status("ready")) {
  let captureStatus = initialStatus;
  const listeners = new Set<(value: typeof initialStatus) => void>();
  const calls = {
    raw: vi.fn(async ({eventId}: {eventId: string; event: Record<string, unknown>;
      sessionId: string}) => ({eventId,
      acceptedTick: 1, inputSequence: 1, coalesced: false,
      replayed: false, projectRevision: null})),
    launch: vi.fn(async ({requestId}: {requestId: string; patternSlot: number}) => ({
      requestId, state: "pending" as const, targetTick: 1920, projectRevision: null,
    })),
    begin: vi.fn(async () => ({performanceId: ids.performance,
      committedRevision: 8, replayed: false, projectRevision: 8})),
    flush: vi.fn(async () => ({performanceId: ids.performance,
      committedRevision: 9, replayed: false, projectRevision: 9})),
    stop: vi.fn(async () => ({requestId: "stop", sessionId: ids.session,
      performanceId: ids.performance, state: "stopped" as const,
      pendingEventCount: 0, replayed: false, projectRevision: null})),
    capture: vi.fn(async (sink: {onStopped(): void}) => ({
      stop: vi.fn(async () => sink.onStopped()),
    })),
  };
  const session = {
    performanceMasterCaptureStatus: () => captureStatus,
    subscribePerformanceMasterCaptureStatus(listener: (value: typeof initialStatus) => void) {
      listeners.add(listener);
      listener(captureStatus);
      return () => listeners.delete(listener);
    },
    startPerformanceMasterCapture: calls.capture,
    beginPerformanceRecording: calls.begin,
    recordPerformanceEvent: calls.raw,
    requestPerformancePatternLaunch: calls.launch,
    flushPerformanceRecording: calls.flush,
    stopPerformanceRecording: calls.stop,
    queryPerformanceRecordingStatus: vi.fn(),
    listPerformances: vi.fn(async () => []),
    inspectPerformance: vi.fn(),
    savePerformance: vi.fn(async () => ({performanceId: ids.performance,
      committedRevision: 10, replayed: false, projectRevision: 10})),
    discardPerformance: vi.fn(),
    listPerformanceRecovery: vi.fn(async () => []),
    applyPerformanceRecovery: vi.fn(), discardPerformanceRecovery: vi.fn(),
    assignPatternSlot: vi.fn(), clearPatternSlot: vi.fn(), movePatternSlot: vi.fn(),
    renamePerformance: vi.fn(), deletePerformance: vi.fn(),
    bindPerformanceRecording: vi.fn(), beginPerformanceReplay: vi.fn(),
    stopPerformanceReplay: vi.fn(),
    // A rendered surface polls replay status every 250 ms for as long as the
    // replay is playing, so any test whose body outlives one tick reaches this
    // mock. `queryPerformanceReplayStatus` is declared to resolve a
    // `PerformanceReplayStatus`, and a bare `vi.fn()` resolves `undefined`,
    // which the controller stores as the replay and `ReplayPanel` then
    // dereferences — the whole surface unmounts mid-test (#713). A poll the
    // Core has not answered yet is the one reply that cannot overwrite state a
    // test staged; a test that wants the poll answered stages it itself.
    queryPerformanceReplayStatus: vi.fn(() => new Promise(() => {})),
    commitPerformanceResample: vi.fn(),
  } as unknown as CreatorPerformanceRuntimeSession;
  return {
    session,
    calls,
    setStatus(next: ReturnType<typeof status>) {
      captureStatus = next;
      for (const listener of listeners) listener(next as typeof initialStatus);
    },
  };
}

function authority(overrides: Record<string, unknown> = {}) {
  return {
    state: "active" as const, sessionId: ids.session,
    performanceId: ids.performance, journalRevision: 1, nextFlushSequence: 1,
    pendingEventCount: 0, openPadGestures: 0, openFxGestures: 0, hold: false,
    pendingLaunch: null, lastLaunchAck: null, projectRevision: null,
    ...overrides,
  };
}

// Gate for the fake-tool-stub-strictness escalation (#726): the Perform
// controller reaches these session methods without any test opting in —
// connect() subscribes the capture status and refreshes the performance and
// recovery lists, and perform_surface.tsx polls refreshReplay every 250 ms.
// A bare vi.fn() resolves undefined where the real session returns a value,
// and the gap only fires when a test outlives one poll tick (#713). Keep the
// list in step with the controller's connect() and interval paths.
test("wall-clock-reachable session double methods keep faithful defaults", () => {
  const reachable = [
    "subscribePerformanceMasterCaptureStatus",
    "listPerformances",
    "listPerformanceRecovery",
    "queryPerformanceReplayStatus",
  ] as const;
  const {session} = sessionFixture();
  for (const method of reachable) {
    const double = session[method];
    const implemented = typeof double === "function" &&
      (!vi.isMockFunction(double) || double.getMockImplementation() !== undefined);
    expect(
      implemented,
      `session double "${method}" is reached by wall-clock (connect() or the ` +
      "250 ms replay poll) but has no default implementation: give it a " +
      "faithful neutral default in sessionFixture, or remove it from the " +
      "controller's wall-clock path",
    ).toBe(true);
  }
});

test("the replay poll default stays neutral and never settles", async () => {
  // Presence is not enough for the 250 ms poll: a production-shaped default
  // that resolves a concrete status can land after a test staged its own
  // state and overwrite it — the second load-sensitive failure #713 traded
  // for the first. The neutral default models a poll the Core has not
  // answered yet, so it must not settle even after microtasks drain.
  const {session} = sessionFixture();
  let settled = false;
  void session.queryPerformanceReplayStatus("replay-1").then(
    () => { settled = true; },
    () => { settled = true; },
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(
    settled,
    "session double \"queryPerformanceReplayStatus\" resolves on its own: " +
    "a poll the test never answered can overwrite staged state when it " +
    "settles late — keep the neutral never-settling default, or let each " +
    "test stage the answer itself",
  ).toBe(false);
});

function controllerFixture(options: {
  captureState?: "unconfigured" | "configured" | "ready" | "unavailable";
  state?: CreatorState;
  opfsAvailable?: boolean;
  maximumStatusQueries?: number;
  waitForStatusQuery?: () => Promise<void>;
} = {}) {
  const runtime = sessionFixture(status(options.captureState ?? "ready"));
  let state = options.state ?? creatorState();
  const order: string[] = [];
  let queueListener: {requestCaptureStop(): void;
    onFailure(failure: {message: string}): void} | null = null;
  let settleQueue!: () => void;
  const settled = new Promise((resolve) => {
    settleQueue = () => {
      order.push("tail-drained");
      resolve({state: "sealed", durableFrames: 100,
        byteLength: 444, reason: "stopped", droppedFrames: 0});
    };
  });
  const store = {
    save: vi.fn(async () => ({committedRevision: 10})),
    discard: vi.fn(async () => ({committedRevision: 10})),
    bind: vi.fn(async () => ({committedRevision: 10})),
  };
  const cleanupTemporary = vi.fn(async () => { order.push("temporary-cleanup"); });
  const captureStop = vi.fn(async () => {
    order.push("capture-stop");
  });
  const dependencies: PerformControllerDependencies = {
    createId: (() => {
      let index = 0;
      return () => [ids.session, ids.performance, `event-${index - 1}`][index++] ?? `id-${index}`;
    })(),
    prepareRecording: vi.fn(async () => {
      order.push("writer");
      return {writer: {} as never, store: store as never, cleanupTemporary};
    }),
    createQueue: vi.fn((_writer, listener) => {
      order.push("queue");
      queueListener = listener;
      return {
        onBatch: vi.fn(), onStopped: () => settleQueue(), onFailure: vi.fn(), settled,
      } as never;
    }),
    ...(options.maximumStatusQueries === undefined
      ? {} : {maximumStatusQueries: options.maximumStatusQueries}),
    ...(options.waitForStatusQuery === undefined
      ? {} : {waitForStatusQuery: options.waitForStatusQuery}),
  };
  runtime.calls.begin.mockImplementation(async () => {
    order.push("begin");
    return {performanceId: ids.performance, committedRevision: 8,
      replayed: false, projectRevision: 8};
  });
  runtime.calls.capture.mockImplementation(async (sink) => {
    order.push("capture");
    return {stop: vi.fn(async () => {
      await captureStop();
      sink.onStopped();
    })};
  });
  runtime.calls.stop.mockImplementation(async () => {
    order.push("core-stop");
    return {requestId: "stop", sessionId: ids.session,
      performanceId: ids.performance, state: "stopped" as const,
      pendingEventCount: 0, replayed: false, projectRevision: null};
  });
  (runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>)
    .mockResolvedValue(authority());
  const refreshProject = vi.fn(async () => { order.push("refresh"); });
  const controller = createPerformController({
    session: runtime.session,
    getCreatorState: () => state,
    refreshProject,
    opfsAvailable: () => options.opfsAvailable ?? true,
    dependencies,
  });
  return {runtime, controller, order, store, refreshProject, cleanupTemporary,
    captureStop, getQueueListener: () => queueListener,
    setCreatorState(next: CreatorState) { state = next; }};
}

function renderSurface(fixture = controllerFixture()) {
  let state = creatorState();
  const onBankChange = vi.fn((bank) => { state = {...state, activeBank: bank}; });
  const rendered = render(
    <PerformSurface controller={fixture.controller} creatorState={state}
      project={project} bank={state.activeBank} onBankChange={onBankChange} />,
  );
  return {fixture, onBankChange, rerender(bank = state.activeBank) {
    state = {...state, activeBank: bank};
    rendered.rerender(<PerformSurface controller={fixture.controller}
      creatorState={state} project={project} bank={bank}
      onBankChange={onBankChange} />);
  }, unmount: rendered.unmount};
}

test("renders Pattern, fixed FX chain, one global HOLD, then the existing Pad surface", () => {
  renderSurface();
  const surface = screen.getByRole("main", {name: "Perform"});
  const pattern = within(surface).getByRole("region", {name: "Pattern Launch"});
  const fx = within(surface).getByRole("region", {name: "Performance FX"});
  const hold = within(surface).getByRole("button", {name: "HOLD"});
  const pads = within(surface).getByRole("region", {name: "Perform instrument"});
  expect(pattern.compareDocumentPosition(fx) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  expect(fx.compareDocumentPosition(hold) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  expect(hold.compareDocumentPosition(pads) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  expect(within(surface).getAllByRole("button", {name: "HOLD"})).toHaveLength(1);
  expect(within(fx).getAllByRole("slider").map((slider) => slider.getAttribute("aria-label")))
    .toEqual(["Filter", "Delay", "Reverb", "Stutter", "Gate", "Reverse", "Crush", "Cutter"]);
});

test("switches Bank synchronously without any Core request", async () => {
  const rendered = renderSurface();
  const before = Object.values(rendered.fixture.runtime.calls)
    .reduce((count, call) => count + call.mock.calls.length, 0);
  await userEvent.click(screen.getByRole("button", {name: "Bank B"}));
  expect(rendered.onBankChange).toHaveBeenCalledWith(1);
  expect(Object.values(rendered.fixture.runtime.calls)
    .reduce((count, call) => count + call.mock.calls.length, 0)).toBe(before);
  rendered.rerender(1);
  expect(screen.getByRole("button", {name: "Bank B"}).getAttribute("aria-pressed"))
    .toBe("true");
  expect(screen.getAllByRole("button", {name: /^Pad B/})).toHaveLength(16);
});

test.each([
  {captureState: "unconfigured" as const, message: null},
  {captureState: "configured" as const, message: "Preparing recording"},
  {captureState: "unavailable" as const, message: "Reload after checking the audio processor URL."},
])("gates Record for $captureState capture", ({captureState, message}) => {
  renderSurface(controllerFixture({captureState}));
  expect(screen.getByRole("button", {name: "Record Performance"}).hasAttribute("disabled"))
    .toBe(true);
  if (message === null) expect(screen.queryByText(/recording (unavailable|preparing)/i)).toBeNull();
  else expect(screen.getByText(message, {exact: false})).not.toBeNull();
});

test.each([
  {name: "Project is not playable", state: creatorState({audio: {phase: "suspended"}}), opfs: true},
  {name: "OPFS is unavailable", state: creatorState(), opfs: false},
])("keeps Record disabled when $name", ({state, opfs}) => {
  renderSurface(controllerFixture({state, opfsAvailable: opfs}));
  expect(screen.getByRole("button", {name: "Record Performance"}).hasAttribute("disabled"))
    .toBe(true);
});

test("keeps Record disabled until recovery discovery completes", async () => {
  const fixture = controllerFixture();
  const recovery = deferred<readonly never[]>();
  (fixture.runtime.session.listPerformanceRecovery as ReturnType<typeof vi.fn>)
    .mockReturnValueOnce(recovery.promise);
  renderSurface(fixture);
  expect(screen.getByRole("button", {name: "Record Performance"})
    .hasAttribute("disabled")).toBe(true);
  recovery.resolve([]);
  await waitFor(() => expect(screen.getByRole("button", {name: "Record Performance"})
    .hasAttribute("disabled")).toBe(false));
});

test("installs writer and queue sink, starts capture, then begins the Core draft", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.capture).toHaveBeenCalledTimes(1));
  expect(fixture.order).toEqual(["writer", "queue", "capture", "begin", "refresh"]);
  expect(fixture.runtime.calls.capture.mock.calls[0]?.[0])
    .toBe(fixture.controller.recordingSink());
});

test("capture start failure cleans the temporary WAV without beginning Core", async () => {
  const fixture = controllerFixture();
  fixture.runtime.calls.capture.mockImplementationOnce(async () => {
    fixture.order.push("capture");
    throw new Error("tap unavailable");
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.cleanupTemporary).toHaveBeenCalledTimes(1));
  expect(fixture.runtime.calls.begin).not.toHaveBeenCalled();
  expect(fixture.order).toEqual(["writer", "queue", "capture", "temporary-cleanup"]);
});

test("capture readiness loss stops the matching Core recording and WAV", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await act(async () => fixture.runtime.setStatus(status("unavailable")));
  await waitFor(() => expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
});

test("capture-stop rejection converges through the controller stop path", async () => {
  const fixture = controllerFixture();
  fixture.captureStop.mockRejectedValueOnce(new Error("tap stop failed"));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));

  fixture.getQueueListener()?.requestCaptureStop();

  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().error).toContain("tap stop failed");
});

test("begin failure stops capture, drains its tail, and removes the temporary WAV", async () => {
  const fixture = controllerFixture();
  fixture.runtime.calls.begin.mockImplementationOnce(async () => {
    fixture.order.push("begin");
    throw new Error("begin rejected");
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.cleanupTemporary).toHaveBeenCalledTimes(1));
  expect(fixture.order).toEqual([
    "writer", "queue", "capture", "begin", "capture-stop", "tail-drained",
    "temporary-cleanup",
  ]);
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
});

test("projection failure after begin discards the stopped Core draft and temporary WAV", async () => {
  const fixture = controllerFixture();
  fixture.refreshProject.mockRejectedValueOnce(new Error("projection failed"));
  renderSurface(fixture);

  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.store.discard).toHaveBeenCalledTimes(1));

  expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.store.discard).toHaveBeenCalledWith({
    expectedRevision: 8,
    performanceId: ids.performance,
  });
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
});

test("retains the sealed WAV and fails closed when projection compensation fails", async () => {
  const fixture = controllerFixture();
  fixture.refreshProject.mockRejectedValueOnce(new Error("projection failed"));
  fixture.store.discard.mockRejectedValueOnce(new Error("discard failed"));
  renderSurface(fixture);

  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.controller.getState().wavStatus).toContain("temporary retained");
  expect(fixture.controller.getState().error).toMatch(/recovery cleanup failed/i);
});

test("default recording resources decorate real writer and store instances through Host seams", async () => {
  const runtime = sessionFixture(status("ready"));
  const writable = {
    seek: vi.fn(async () => {}), write: vi.fn(async () => {}),
    truncate: vi.fn(async () => {}), close: vi.fn(async () => {}),
    abort: vi.fn(async () => {}),
  };
  const file = {name: "temporary.wav",
    createWritable: vi.fn(async () => writable)};
  const temporary = {
    getFileHandle: vi.fn(async () => file), removeEntry: vi.fn(async () => {}),
  };
  const managed = {
    getFileHandle: vi.fn(), removeEntry: vi.fn(async () => {}),
  };
  const projectDirectory = {getDirectoryHandle: vi.fn(async () => managed)};
  const projectsDirectory = {getDirectoryHandle: vi.fn(async () => projectDirectory)};
  const root = {getDirectoryHandle: vi.fn(async (name: string) =>
    name === "lmdj-perform-temporary" ? temporary : projectsDirectory)};
  const previousStorage = navigator.storage;
  const previousSeams = (window as Window & {__LMDJ_WEB_HOST_SEAMS__?: unknown})
    .__LMDJ_WEB_HOST_SEAMS__;
  const createWavStreamWriter = vi.fn(async (real) => real);
  const createPerformanceRecordingStore = vi.fn(async (real) => real);
  Object.defineProperty(navigator, "storage", {configurable: true,
    value: {getDirectory: vi.fn(async () => root)}});
  Object.defineProperty(window, "__LMDJ_WEB_HOST_SEAMS__", {configurable: true,
    value: {createWavStreamWriter, createPerformanceRecordingStore}});
  try {
    const controller = createPerformController({
      session: runtime.session,
      getCreatorState: () => creatorState(),
      refreshProject: vi.fn(async () => {}),
      opfsAvailable: () => true,
      dependencies: {createId: (() => { let id = 0; return () => `id-${++id}`; })()},
    });
    await controller.refreshRecovery();
    await controller.record();
    expect(createWavStreamWriter).toHaveBeenCalledTimes(1);
    expect(createWavStreamWriter.mock.calls[0]?.[0]).toMatchObject({
      appendChannels: expect.any(Function), seal: expect.any(Function),
    });
    expect(createPerformanceRecordingStore).toHaveBeenCalledTimes(1);
    expect(createPerformanceRecordingStore.mock.calls[0]?.[0]).toMatchObject({
      save: expect.any(Function), discard: expect.any(Function),
    });
    expect(root.getDirectoryHandle).toHaveBeenCalledWith("projects");
    expect(projectsDirectory.getDirectoryHandle)
      .toHaveBeenCalledWith(`${ids.project}.lmdj`);
    expect(projectDirectory.getDirectoryHandle).toHaveBeenCalledWith("assets");
    await controller.close();
  } finally {
    Object.defineProperty(navigator, "storage", {configurable: true,
      value: previousStorage});
    Object.defineProperty(window, "__LMDJ_WEB_HOST_SEAMS__", {configurable: true,
      value: previousSeams});
  }
});

test("forwards every FX raw value with exact Core keys and no Host clock or source", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  const filter = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "630"}});
  fireEvent.change(filter, {target: {value: "631"}});
  fireEvent.pointerUp(filter, {pointerId: 3});
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(4));
  const requests = fixture.runtime.calls.raw.mock.calls.map(([request]) => request);
  expect(requests.map(({event}) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_move", "fx_release"]);
  expect(requests[1]?.event).toMatchObject({fx: "filter", value: 630});
  expect(requests[2]?.event).toMatchObject({fx: "filter", value: 631});
  for (const request of requests) {
    expect(Object.keys(request).sort()).toEqual(["event", "eventId", "sessionId"]);
    expect(request.event).not.toHaveProperty("source");
    expect(request.event).not.toHaveProperty("tick");
    expect(request.event).not.toHaveProperty("runtimeFrame");
    expect(request.event).not.toHaveProperty("inputSequence");
  }
});

test("closes active gestures on stop and rejects their releases in the next recording", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "pad-old",
    slot: 0, velocity: 100});
  fixture.controller.engageFx("filter", 650);
  await fixture.controller.stop();
  const firstKinds = fixture.runtime.calls.raw.mock.calls.map(([request]) =>
    request.event.kind);
  expect(firstKinds).toEqual(["pad_press", "fx_engage", "pad_release", "fx_release"]);

  await fixture.controller.discard();
  await fixture.controller.record();
  const before = fixture.runtime.calls.raw.mock.calls.length;
  await fixture.controller.recordRawEvent({kind: "pad_release", gestureId: "pad-old", slot: 0});
  expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(before);
});

test("serializes Stop after an in-flight Flush", async () => {
  const fixture = controllerFixture();
  const flush = deferred<{performanceId: string; committedRevision: number;
    replayed: false; projectRevision: number}>();
  fixture.runtime.calls.flush.mockReturnValueOnce(flush.promise);
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  await fixture.controller.record();

  const flushing = fixture.controller.flush();
  const stopping = fixture.controller.stop();
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  flush.resolve({performanceId: ids.performance, committedRevision: 9,
    replayed: false, projectRevision: 9});
  await Promise.all([flushing, stopping]);
  expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
});

test("keeps admitting raw Pad events while Flush writes the active draft", async () => {
  const fixture = controllerFixture();
  const flush = deferred<{performanceId: string; committedRevision: number;
    replayed: false; projectRevision: number}>();
  fixture.runtime.calls.flush.mockReturnValueOnce(flush.promise);
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  await fixture.controller.record();

  const flushing = fixture.controller.flush();
  expect(fixture.controller.getState().recording.phase).toBe("flushing");
  await fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "during-flush",
    slot: 0, velocity: 100});
  expect(fixture.runtime.calls.raw).toHaveBeenCalledWith(expect.objectContaining({
    event: {kind: "pad_press", gestureId: "during-flush", slot: 0, velocity: 100},
  }));
  flush.resolve({performanceId: ids.performance, committedRevision: 9,
    replayed: false, projectRevision: 9});
  await flushing;
});

test("closes raw admission before Stop drains its synthetic releases", async () => {
  const fixture = controllerFixture();
  const firstEvent = deferred<{eventId: string; acceptedTick: number;
    inputSequence: number; coalesced: false; replayed: false; projectRevision: null}>();
  fixture.runtime.calls.raw.mockReturnValueOnce(firstEvent.promise);
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  await fixture.controller.record();
  const first = fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "open",
    slot: 0, velocity: 100});
  const stopping = fixture.controller.stop();
  expect(fixture.controller.getState().recording.phase).toBe("stopping");
  await fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "too-late",
    slot: 1, velocity: 100});
  expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(1);
  firstEvent.resolve({eventId: "event", acceptedTick: 1, inputSequence: 1,
    coalesced: false, replayed: false, projectRevision: null});
  await Promise.all([first, stopping]);
  expect(fixture.runtime.calls.raw.mock.calls.map(([request]) => request.event.gestureId))
    .toEqual(["open", "open"]);
});

test("keeps Pattern launch pending until query reports the actual acknowledgement", async () => {
  const fixture = controllerFixture();
  const query = fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>;
  query.mockResolvedValueOnce(authority({
    pendingLaunch: {requestId: "event-1", patternSlot: 0, targetTick: 1920, claimed: false},
  }));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Launch Pattern 1"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Launch Pattern 1"})
    .getAttribute("aria-busy")).toBe("true"));
  query.mockResolvedValueOnce(authority({journalRevision: 2,
    lastLaunchAck: {requestId: "event-1", patternSlot: 0, effectiveTick: 1920}}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Launch Pattern 1"})
    .getAttribute("aria-busy")).toBe("false"));
});

test("does not invent pending UI when the first authority query already has the ack", async () => {
  const fixture = controllerFixture();
  const query = fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>;
  query.mockResolvedValueOnce(authority({
    lastLaunchAck: {requestId: "event-1", patternSlot: 0, effectiveTick: 1920},
  }));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Launch Pattern 1"}));
  await waitFor(() => expect(fixture.runtime.calls.launch).toHaveBeenCalledTimes(1));
  expect(screen.getByRole("button", {name: "Launch Pattern 1"})
    .getAttribute("aria-busy")).toBe("false");
});

test("cancels an unacknowledged launch observer when recording stops", async () => {
  const fixture = controllerFixture();
  const query = fixture.runtime.session.queryPerformanceRecordingStatus as
    ReturnType<typeof vi.fn>;
  query.mockResolvedValue(authority({
    pendingLaunch: {requestId: "event-1", patternSlot: 0, targetTick: 1920,
      claimed: false},
  }));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  const launching = fixture.controller.launchPattern(0);
  await waitFor(() => expect(fixture.runtime.calls.launch).toHaveBeenCalledTimes(1));
  await fixture.controller.stop();
  await launching;
  expect(fixture.controller.getState().error).toBeNull();
});

test("assigns, clears, and moves slots only through Facade then projection refresh", async () => {
  const {fixture} = renderSurface();
  const session = fixture.runtime.session;
  (session.assignPatternSlot as ReturnType<typeof vi.fn>).mockResolvedValue({
    patternSlot: 2, patternId: ids.pattern2, committedRevision: 8,
    replayed: false, projectRevision: 8,
  });
  (session.clearPatternSlot as ReturnType<typeof vi.fn>).mockResolvedValue({
    patternSlot: 0, patternId: null, committedRevision: 9,
    replayed: false, projectRevision: 9,
  });
  (session.movePatternSlot as ReturnType<typeof vi.fn>).mockResolvedValue({
    fromSlot: 0, toSlot: 3, patternId: ids.pattern1,
    committedRevision: 10, replayed: false, projectRevision: 10,
  });
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Pattern assignment"}),
    ids.pattern2);
  fireEvent.change(screen.getByRole("combobox", {name: "Pattern slot"}),
    {target: {value: "2"}});
  await userEvent.click(screen.getByRole("button", {name: "Assign Pattern"}));
  fireEvent.change(screen.getByRole("combobox", {name: "Clear Pattern slot"}),
    {target: {value: "0"}});
  await userEvent.click(screen.getByRole("button", {name: "Clear Pattern"}));
  fireEvent.change(screen.getByRole("combobox", {name: "Move Pattern from"}),
    {target: {value: "0"}});
  fireEvent.change(screen.getByRole("combobox", {name: "Move Pattern to"}),
    {target: {value: "3"}});
  await userEvent.click(screen.getByRole("button", {name: "Move Pattern"}));
  await waitFor(() => expect(fixture.refreshProject).toHaveBeenCalledTimes(3));
  expect(session.assignPatternSlot).toHaveBeenCalledWith({expectedRevision: 7,
    patternSlot: 2, patternId: ids.pattern2});
  expect(session.clearPatternSlot).toHaveBeenCalledWith({expectedRevision: 8,
    patternSlot: 0});
  expect(session.movePatternSlot).toHaveBeenCalledWith({expectedRevision: 9,
    fromSlot: 0, toSlot: 3});
  expect(project.patternSlots[2]).toBeNull();
});

test("serializes Project mutations through one projection refresh lane", async () => {
  const fixture = controllerFixture();
  const assigned = deferred<{patternSlot: number; patternId: string;
    committedRevision: number; replayed: false; projectRevision: number}>();
  (fixture.runtime.session.assignPatternSlot as ReturnType<typeof vi.fn>)
    .mockReturnValueOnce(assigned.promise);
  (fixture.runtime.session.clearPatternSlot as ReturnType<typeof vi.fn>)
    .mockResolvedValue({patternSlot: 0, patternId: null, committedRevision: 9,
      replayed: false, projectRevision: 9});

  const assigning = fixture.controller.assignPattern(1, ids.pattern2);
  const clearing = fixture.controller.clearPattern(0);
  expect(fixture.runtime.session.clearPatternSlot).not.toHaveBeenCalled();
  assigned.resolve({patternSlot: 1, patternId: ids.pattern2, committedRevision: 8,
    replayed: false, projectRevision: 8});
  await Promise.all([assigning, clearing]);
  expect(fixture.runtime.session.clearPatternSlot).toHaveBeenCalledWith({
    expectedRevision: 8, patternSlot: 0,
  });
  expect(fixture.refreshProject).toHaveBeenCalledTimes(2);
});

test("stops capture, saves the named draft, then binds the WAV", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Flush Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  expect(fixture.order.slice(-3)).toEqual(["core-stop", "capture-stop", "tail-drained"]);
  await userEvent.clear(screen.getByRole("textbox", {name: "Performance name"}));
  await userEvent.type(screen.getByRole("textbox", {name: "Performance name"}), "Night Set");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledWith({
    expectedRevision: 9,
    performanceId: ids.performance,
    name: "Night Set",
    recordingArtifact: null,
  });
  expect(fixture.store.bind).toHaveBeenCalledWith({expectedRevision: 10,
    performanceId: ids.performance});
  expect(fixture.store.save).not.toHaveBeenCalled();
  expect(fixture.refreshProject).toHaveBeenCalledTimes(4);
  expect(screen.getByRole("status", {name: "WAV binding status"}).textContent)
    .toContain("bound");
});

test("keeps a busy save stopped and makes the same action explicitly retryable", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.savePerformance as ReturnType<typeof vi.fn>)
    .mockRejectedValueOnce(Object.assign(
      new Error("Host request was rejected"), {code: "PROJECT_BUSY"},
    ));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));

  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toMatch(/Project is busy.*retry Save Performance/i));
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  expect(screen.getByRole("button", {name: "Save Performance"})
    .hasAttribute("disabled")).toBe(false);
  expect(fixture.store.bind).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(fixture.runtime.session.savePerformance)
    .toHaveBeenCalledTimes(2));
  await waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole("alert")).toBeNull();
});

test("binds with the latest Project revision after a concurrent mutation", async () => {
  const {fixture} = renderSurface();
  await waitFor(() => expect(fixture.runtime.session.listPerformances)
    .toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByRole("button", {name: "Record Performance"})
    .hasAttribute("disabled")).toBe(false));
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));

  const performances = deferred<readonly never[]>();
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockReturnValueOnce(performances.promise);
  (fixture.runtime.session.commitPerformanceResample as ReturnType<typeof vi.fn>)
    .mockResolvedValue({performanceId: ids.performance, committedRevision: 11,
      runtimePrepareRequired: true, projectRevision: 11});

  const saving = fixture.controller.save("Concurrent Set");
  await vi.waitFor(() => expect(fixture.runtime.session.listPerformances)
    .toHaveBeenCalledTimes(2));

  await fixture.controller.resample(ids.performance, 0, 4_800, 0);
  expect(fixture.runtime.session.commitPerformanceResample).toHaveBeenCalledWith({
    expectedRevision: 10, performanceId: ids.performance,
    sourceStartFrame: 0, sourceEndFrame: 4_800, targetSlot: 0,
  });
  performances.resolve([]);
  await saving;

  expect(fixture.store.bind).toHaveBeenCalledWith({expectedRevision: 11,
    performanceId: ids.performance});
});

test("retains a failed WAV binding for an explicit retry without saving twice", async () => {
  const fixture = controllerFixture();
  fixture.store.bind.mockRejectedValueOnce(Object.assign(
    new Error("deterministic bind contention"), {code: "PROJECT_BUSY"},
  ));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Retry WAV bind"}))
    .not.toBeNull());

  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert").textContent).toMatch(/WAV.*bind.*retry/i);
  await userEvent.click(screen.getByRole("button", {name: "Retry WAV bind"}));
  await waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(2));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status", {name: "WAV binding status"}).textContent)
    .toContain("bound");
});

test("retries Project projection after save without saving the Performance twice", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  fixture.refreshProject.mockRejectedValueOnce(new Error("projection failed"));
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toMatch(/saved.*Project.*refresh.*retry/i));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.store.bind).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.phase).toBe("stopped");

  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(1));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
  expect(fixture.controller.getState().recording.phase).toBe("idle");
});

test("retries the saved Performance list projection before binding", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await waitFor(() => expect(fixture.runtime.session.listPerformances)
    .toHaveBeenCalledTimes(1));
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockRejectedValueOnce(new Error("list failed"));

  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toMatch(/saved.*Project.*refresh.*retry/i));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.store.bind).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(1));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("idle");
});

test("retries projection after a committed WAV bind without binding twice", async () => {
  const fixture = controllerFixture();
  fixture.store.bind.mockImplementationOnce(async () => {
    fixture.refreshProject.mockRejectedValueOnce(new Error("projection failed"));
    return {committedRevision: 11};
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Retry WAV bind"}))
    .not.toBeNull());
  expect(fixture.store.bind).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");

  await userEvent.click(screen.getByRole("button", {name: "Retry WAV bind"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("idle"));
  expect(fixture.store.bind).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
});

test("reconciles a lost save response before binding and never resubmits save", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.savePerformance as ReturnType<typeof vi.fn>)
    .mockRejectedValueOnce(Object.assign(new Error("response lost"), {
      code: "HOST_TIMEOUT",
    }));
  (fixture.runtime.session.inspectPerformance as ReturnType<typeof vi.fn>)
    .mockResolvedValue({id: ids.performance, name: "Lost Reply", createdBpm: 120,
      recordingArtifact: null, events: [], projectRevision: 10});
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await userEvent.clear(screen.getByRole("textbox", {name: "Performance name"}));
  await userEvent.type(screen.getByRole("textbox", {name: "Performance name"}), "Lost Reply");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));

  await waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(1));
  expect(fixture.runtime.session.inspectPerformance).toHaveBeenCalledWith(ids.performance);
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("idle");
});

test("retries projection after committed discard without discarding twice", async () => {
  const fixture = controllerFixture();
  fixture.store.discard.mockImplementationOnce(async () => {
    fixture.refreshProject.mockRejectedValueOnce(new Error("projection failed"));
    return {committedRevision: 9};
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Discard Performance"}));
  await waitFor(() => expect(fixture.store.discard).toHaveBeenCalledTimes(1));
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  expect(screen.getByRole("alert").textContent).toMatch(/discarded.*refresh.*retry/i);

  await userEvent.click(screen.getByRole("button", {name: "Discard Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("idle"));
  expect(fixture.store.discard).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().wavStatus).toContain("temporary removed");
});

test("renders authoritative recording, WAV, launch, replay, recovery and resample status", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{performanceId: ids.performance, name: "Take 1",
      createdBpm: 120, recordingArtifact: null, eventCount: 4}]);
  (fixture.runtime.session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  (fixture.runtime.session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", requestId: "stop-replay", state: "stopped",
      resolvedRevision: 7, eventCursor: 2, eventCount: 4, replayed: false,
      projectRevision: null});
  (fixture.runtime.session.commitPerformanceResample as ReturnType<typeof vi.fn>)
    .mockResolvedValue({performanceId: ids.performance, committedRevision: 8,
      runtimePrepareRequired: true, projectRevision: 8});
  (fixture.runtime.session.applyPerformanceRecovery as ReturnType<typeof vi.fn>)
    .mockResolvedValue({performanceId: ids.performance, committedRevision: 9,
      replayed: false, projectRevision: 9});
  renderSurface(fixture);

  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await fixture.controller.refreshAuthority();
  expect(screen.getByRole("status", {name: "Performance recording status"}).textContent)
    .toMatch(/open Pads.*0.*open FX.*0.*HOLD.*off/i);
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(screen.getByRole("status", {name: "WAV recording status"})
    .textContent).toContain("sealed · stopped"));

  await userEvent.click(await screen.findByRole("button", {name: "Replay Take 1"}));
  expect(screen.getByRole("status", {name: "Replay status"}).textContent)
    .toContain("resolved revision · 7");
  await userEvent.click(screen.getByRole("button", {name: "Stop Replay"}));
  expect(screen.getByRole("status", {name: "Replay status"}).textContent)
    .toContain("stopped · neutral");

  (fixture.runtime.session.listPerformanceRecovery as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{sessionId: ids.session, performanceId: ids.performance,
      reason: "owner_lost", durableEventCount: 1, pendingEventCount: 1,
      fingerprint: "f".repeat(64)}]);
  await fixture.controller.refreshRecovery();
  await userEvent.click(screen.getByRole("button", {name: "Apply recovery"}));
  await waitFor(() => expect(screen.getByRole("status", {
    name: "Performance recovery status",
  }).textContent).toMatch(/applied.*closed.*Pad/i));

  await fixture.controller.resample(ids.performance, 0, 4_800, 16);
  expect(screen.getByRole("status", {name: "Resample status"}).textContent)
    .toContain("committed · Pad B1");
});

test("blocks a second recording while owner-loss recovery is actionable", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.listPerformanceRecovery as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{sessionId: ids.session, performanceId: ids.performance,
      reason: "owner_lost", durableEventCount: 1, pendingEventCount: 1,
      fingerprint: "f".repeat(64)}]);
  renderSurface(fixture);
  await fixture.controller.refreshRecovery();
  await waitFor(() => expect(screen.getByRole("button", {name: "Record Performance"})
    .hasAttribute("disabled")).toBe(true));
  expect(screen.getByRole("status", {name: "Performance recovery status"}).textContent)
    .toContain("owner lost");
});

test("unmount closes an active recording once without saving", async () => {
  const rendered = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(rendered.fixture.runtime.calls.begin).toHaveBeenCalledTimes(1));
  rendered.unmount();
  await rendered.fixture.controller.close();
  await waitFor(() => expect(rendered.fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  expect(rendered.fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(rendered.fixture.store.save).not.toHaveBeenCalled();
});

test("leaving and reopening Perform does not permanently close its Project controller", async () => {
  const rendered = renderSurface();
  rendered.unmount();
  await waitFor(() => expect(rendered.fixture.controller.canRecord()).toBe(true));
  renderSurface(rendered.fixture);
  expect(screen.getByRole("button", {name: "Record Performance"})
    .hasAttribute("disabled")).toBe(false);
});

test("leaving Perform stops active replay before the controller is reused", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{performanceId: ids.performance, name: "Take 1",
      createdBpm: 120, recordingArtifact: null, eventCount: 4}]);
  (fixture.runtime.session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  (fixture.runtime.session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", requestId: "stop-replay",
      state: "stopped", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      replayed: false, projectRevision: null});
  const rendered = renderSurface(fixture);
  await userEvent.click(await screen.findByRole("button", {name: "Replay Take 1"}));
  rendered.unmount();
  await waitFor(() => expect(fixture.runtime.session.stopPerformanceReplay)
    .toHaveBeenCalledTimes(1));
});

test("retries replay neutral reset until Core reports a terminal state", async () => {
  const fixture = controllerFixture();
  const session = fixture.runtime.session;
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  (session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockRejectedValueOnce(new Error("reset failed"))
    .mockResolvedValueOnce({replayId: "replay-1", requestId: "retry-1",
      state: "playing", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      replayed: false, projectRevision: null})
    .mockResolvedValueOnce({replayId: "replay-1", requestId: "retry-2",
      state: "stopped", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      replayed: false, projectRevision: null});
  await fixture.controller.beginReplay(ids.performance);
  await fixture.controller.stopReplay();
  expect(session.stopPerformanceReplay).toHaveBeenCalledTimes(3);
  expect(fixture.controller.getState().replay?.state).toBe("stopped");
  expect(fixture.controller.getState().replayNeutral).toBe(true);
});

test("refuses to leave while replay neutral reset remains pending", async () => {
  const fixture = controllerFixture({maximumStatusQueries: 2,
    waitForStatusQuery: async () => {}});
  const session = fixture.runtime.session;
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  (session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", requestId: "pending",
      state: "playing", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      replayed: false, projectRevision: null});
  await fixture.controller.beginReplay(ids.performance);
  await expect(fixture.controller.leave()).rejects.toThrow(/neutral reset timed out/i);
  expect(fixture.controller.getState().replay?.state).toBe("playing");
  expect(fixture.controller.getState().replayNeutral).toBe(false);
});

test("renders named replay and editable resample controls", async () => {
  const fixture = controllerFixture();
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{
      performanceId: ids.performance, name: "Take 1", createdBpm: 120,
      recordingArtifact: null, eventCount: 4,
    }]);
  (fixture.runtime.session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  (fixture.runtime.session.commitPerformanceResample as ReturnType<typeof vi.fn>)
    .mockResolvedValue({performanceId: ids.performance, committedRevision: 8,
      runtimePrepareRequired: true, projectRevision: 8});
  renderSurface(fixture);
  await userEvent.click(await screen.findByRole("button", {name: "Replay Take 1"}));
  expect(screen.getByRole("status", {name: "Replay status"}).textContent).toContain("playing");
  await userEvent.clear(screen.getByRole("spinbutton", {name: "Resample start frame"}));
  await userEvent.type(screen.getByRole("spinbutton", {name: "Resample start frame"}), "120");
  await userEvent.clear(screen.getByRole("spinbutton", {name: "Resample end frame"}));
  await userEvent.type(screen.getByRole("spinbutton", {name: "Resample end frame"}), "4800");
  await userEvent.clear(screen.getByRole("spinbutton", {name: "Resample target Pad"}));
  await userEvent.type(screen.getByRole("spinbutton", {name: "Resample target Pad"}), "17");
  await userEvent.click(screen.getByRole("button", {name: "Resample selection"}));
  await waitFor(() => expect(fixture.runtime.session.commitPerformanceResample)
    .toHaveBeenCalledWith({expectedRevision: 7, performanceId: ids.performance,
      sourceStartFrame: 120, sourceEndFrame: 4800, targetSlot: 17}));
});

test("discards the stopped WAV through the store and refreshes Project truth", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  await userEvent.click(screen.getByRole("button", {name: "Discard Performance"}));
  expect(fixture.store.discard).toHaveBeenCalledWith({expectedRevision: 8,
    performanceId: ids.performance});
  expect(fixture.refreshProject).toHaveBeenCalledTimes(2);
});

test("lists, replays, resamples, and recovers through Facade operations", async () => {
  const fixture = controllerFixture();
  const session = fixture.runtime.session;
  (session.listPerformances as ReturnType<typeof vi.fn>).mockResolvedValueOnce([{
    performanceId: ids.performance, name: "Take 1", createdBpm: 120,
    recordingArtifact: null, eventCount: 4,
  }]);
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>).mockResolvedValue({
    replayId: "replay-1", state: "playing", resolvedRevision: 7,
    eventCursor: 0, eventCount: 4, projectRevision: null,
  });
  (session.stopPerformanceReplay as ReturnType<typeof vi.fn>).mockResolvedValue({
    replayId: "replay-1", requestId: "stop-replay", state: "stopped",
    resolvedRevision: 7, eventCursor: 2, eventCount: 4,
    replayed: false, projectRevision: null,
  });
  (session.commitPerformanceResample as ReturnType<typeof vi.fn>).mockResolvedValue({
    performanceId: ids.performance, committedRevision: 8,
    runtimePrepareRequired: true, projectRevision: 8,
  });
  (session.applyPerformanceRecovery as ReturnType<typeof vi.fn>).mockResolvedValue({
    performanceId: ids.performance, committedRevision: 9,
    replayed: false, projectRevision: 9,
  });
  await fixture.controller.refreshPerformances();
  await fixture.controller.beginReplay(ids.performance);
  fixture.controller.engageFx("filter", 720);
  fixture.controller.toggleHold();
  await fixture.controller.stopReplay();
  await fixture.controller.resample(ids.performance, 0, 48_000, 4);
  await fixture.controller.applyRecovery(ids.session);
  expect(session.beginPerformanceReplay).toHaveBeenCalledWith({
    replayId: expect.any(String), performanceId: ids.performance,
  });
  expect(session.commitPerformanceResample).toHaveBeenCalledWith({
    expectedRevision: 7, performanceId: ids.performance,
    sourceStartFrame: 0, sourceEndFrame: 48_000, targetSlot: 4,
  });
  expect(session.applyPerformanceRecovery).toHaveBeenCalledWith({
    expectedRevision: 8, sessionId: ids.session,
  });
  expect(fixture.refreshProject).toHaveBeenCalledTimes(2);
  expect(fixture.controller.getState().replay?.state).toBe("stopped");
  expect(fixture.controller.getState().hold).toBe(false);
  expect(Object.values(fixture.controller.getState().fx)).toEqual(Array(8).fill(500));
  expect(fixture.controller.getState().pendingLaunch).toBeNull();
  expect(fixture.controller.getState().lastLaunchAck).toBeNull();
});
