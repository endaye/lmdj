import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import type {ContextualEncoders} from "../src/components/physical_controls";
import type {PatternTransportStatus} from "@lmdj/web-runtime-platform/runtime_types";
import {PerformSurface} from "../src/components/perform_surface";
import {PerformOverview} from "../src/components/perform_overview";
import type {CreatorPerformanceRuntimeSession} from "../src/runtime/runtime_types";
import {
  initialPatternTransportState,
  type PatternTransportState,
} from "../src/state/pattern_transport_state";
import {
  createPerformController,
  cutoffHzToPosition,
  cutoffPositionToHz,
  selectLivePadGate,
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

const LIVE_EPOCH = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

function liveGateState(value = 0) {
  return {engaged: false, frozen: false, value};
}

function liveState(overrides: Record<string, unknown> = {}) {
  return {
    hold: false,
    filter: {mode: "independent" as const, engaged: false, frozen: false,
      type: "lp" as const, cutoffHz: 20000, resonanceMilli: 0},
    otherFx: {
      delay: liveGateState(), reverb: liveGateState(),
      stutter: liveGateState(), gate: liveGateState(),
      reverse: liveGateState(), crush: liveGateState(),
      cutter: liveGateState(),
    },
    mutedSlots: [] as number[], soloSlots: [] as number[],
    ...overrides,
  };
}

function liveStatusUnavailable() {
  return {
    available: false as const, controlEpoch: null, accepted: null,
    applied: null, acceptedControlSequence: null, appliedControlSequence: null,
    resetPending: false, beginPending: false, projectRevision: null,
  };
}

function liveStatusAvailable(overrides: Record<string, unknown> = {}) {
  return {
    available: true as const, controlEpoch: LIVE_EPOCH,
    accepted: liveState(), applied: liveState(),
    runtimeGenerations: {
      filter: null, delay: null, reverb: null, stutter: null,
      gate: null, reverse: null, crush: null, cutter: null,
    },
    acceptedControlSequence: "0", appliedControlSequence: "0",
    resetPending: false, beginPending: false, projectRevision: null,
    ...overrides,
  };
}

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
    category: null, colourOverride: null, colour: null,
  })),
  patterns: [
    {patternId: ids.pattern1, bars: 1 as const, events: []},
    {patternId: ids.pattern2, bars: 4 as const, events: []},
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

function status(
  state: "unconfigured" | "configured" | "ready" | "unavailable",
  code: "tap-initialization-failed" | "tap-processor-failed" = "tap-initialization-failed",
) {
  const config = state === "unconfigured" ? null : {
    performRecordingFrames: 86_400_000,
    performRecordingQueueBatches: 32,
  };
  return state === "unavailable" ? {
    state,
    config,
    error: {code,
      message: "Reload after checking the audio processor URL."},
  } : {state, config, error: null};
}

function sessionFixture(initialStatus = status("ready")) {
  let captureStatus = initialStatus;
  let liveCommandIndex = 0;
  const listeners = new Set<(value: typeof initialStatus) => void>();
  const calls = {
    // The raw/begin doubles keep loose promise shapes so a test can stage the
    // headered profile's receipts; the session cast pins the real contract.
    raw: vi.fn(async ({eventId}: {eventId: string; event: Record<string, unknown>;
      sessionId: string}): Promise<unknown> => ({eventId,
      acceptedTick: 1, inputSequence: 1, coalesced: false,
      replayed: false, projectRevision: null})),
    fx: vi.fn(async (_event: Record<string, unknown>) => ({applied: true as const})),
    launch: vi.fn(async ({requestId}: {requestId: string; patternSlot: number}) => ({
      requestId, state: "pending" as const, targetTick: 1920, projectRevision: null,
    })),
    begin: vi.fn(async (_request?: Record<string, unknown>): Promise<unknown> =>
      ({performanceId: ids.performance,
        committedRevision: 8, replayed: false, projectRevision: 8})),
    flush: vi.fn(async () => ({performanceId: ids.performance,
      committedRevision: 9, replayed: false, projectRevision: 9})),
    stop: vi.fn(async () => ({requestId: "stop", sessionId: ids.session,
      performanceId: ids.performance, state: "stopped" as const,
      pendingEventCount: 0, replayed: false, projectRevision: null})),
    capture: vi.fn(async (sink: {onStopped(): void}) => ({
      stop: vi.fn(async () => sink.onStopped()),
    })),
    // The typed producer defaults to the honest unavailable answer (headless /
    // pre-W1 Core): every legacy path above keeps its existing behaviour, and
    // typed tests stage an available status themselves. The mock's return type
    // stays loose so both answers fit; the session cast pins the real shape.
    liveStatus: vi.fn(async (): Promise<unknown> => liveStatusUnavailable()),
    liveControl: vi.fn(async ({controlEpoch, intent}: {
      controlEpoch: string;
      intent: {kind: string; phase?: string; gestureGeneration?: string};
    }) => {
      liveCommandIndex += 1;
      return {
        commandId: `command-${liveCommandIndex}`,
        controlEpoch, controlSequence: `${liveCommandIndex}`,
        gestureGeneration: intent.kind === "fx_release" ||
            intent.kind === "filter_release" ? null
          : intent.phase === "move" ? null
          : `generation-${liveCommandIndex}`,
        accepted: true as const, applied: true,
        replayed: false, projectRevision: null,
      };
    }),
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
    applyFxGesture: calls.fx,
    applyPerformanceLiveControl: calls.liveControl,
    queryPerformanceLiveStatus: calls.liveStatus,
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
// recovery lists plus the live-control status, and perform_surface.tsx polls
// refreshReplay every 250 ms.
// A bare vi.fn() resolves undefined where the real session returns a value,
// and the gap only fires when a test outlives one poll tick (#713). Keep the
// list in step with the controller's connect() and interval paths.
test("wall-clock-reachable session double methods keep faithful defaults", () => {
  const reachable = [
    "subscribePerformanceMasterCaptureStatus",
    "listPerformances",
    "listPerformanceRecovery",
    "queryPerformanceLiveStatus",
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
  reportFailure?: (operation: string, error: unknown) => unknown;
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
    ...(options.reportFailure === undefined ? {} : {reportFailure: options.reportFailure}),
  });
  return {runtime, controller, order, store, refreshProject, cleanupTemporary,
    captureStop, getQueueListener: () => queueListener,
    setCreatorState(next: CreatorState) { state = next; }};
}

function renderSurface(fixture = controllerFixture()) {
  let state = creatorState();
  const rendered = render(
    <PerformSurface controller={fixture.controller}
      project={project} bank={state.activeBank} />,
  );
  return {fixture, rerender(bank = state.activeBank) {
    state = {...state, activeBank: bank};
    rendered.rerender(<PerformSurface controller={fixture.controller}
      project={project} bank={bank} />);
  }, unmount: rendered.unmount};
}

function selectPerformPage(name: "Live" | "Slots" | "Takes" | "Replay") {
  const button = within(screen.getByRole("navigation", {name: "Perform pages"}))
    .getByRole("button", {name});
  if (button.getAttribute("aria-current") !== "page") fireEvent.click(button);
}

function idlePatternTransport(): PatternTransportState {
  return {
    ...initialPatternTransportState,
    sessionId: "session-1",
    status: {
      engaged: true, playing: false, recording: false, phase: "idle",
      runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
      observedAtMilliseconds: 0, commandId: null, publicationPending: false,
      error: null, currentPatternId: ids.pattern1, pendingSwitch: null,
    },
  };
}

test("renders Pattern, fixed FX chain, one global HOLD, then the existing Pad surface", () => {
  renderSurface();
  const surface = screen.getByRole("main", {name: "Perform"});
  const pattern = within(surface).getByRole("region", {name: "Pattern Launch"});
  const fx = within(surface).getByRole("region", {name: "Performance FX"});
  const hold = within(surface).getByRole("button", {name: "HOLD"});
  // The console's Pad matrix is the one Pad surface; Perform mounts none of
  // its own, so a second identical grid never competes for the same names.
  expect(within(surface).queryByRole("region", {name: "Perform instrument"})).toBeNull();
  expect(pattern.compareDocumentPosition(fx) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  expect(fx.compareDocumentPosition(hold) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
  expect(within(surface).getAllByRole("button", {name: "HOLD"})).toHaveLength(1);
  expect(within(fx).getAllByRole("slider").map((slider) => slider.getAttribute("aria-label")))
    .toEqual(["Filter", "Delay", "Reverb"]);
  for (const pictured of ["LP", "HP", "BP", "MASTER", "MUTE", "SOLO"]) {
    expect(within(surface).queryByRole("slider", {name: pictured})).toBeNull();
    expect(within(surface).queryByRole("button", {name: pictured})).toBeNull();
  }
});

// #1958: without a Performance recording, a Launch slot selects its Pattern
// through the app's Sequence selection path — the app queues the transport
// switch while playing and reloads the snapshot while stopped — and an empty
// slot does nothing.
test("Launch without a Performance recording selects the slot's Pattern; empty slots do nothing", async () => {
  const fixture = controllerFixture();
  const onSelectPattern = vi.fn();
  const transport = (overrides: Partial<PatternTransportStatus>): PatternTransportState => ({
    ...initialPatternTransportState,
    sessionId: "session-1",
    status: {
      engaged: true, playing: true, recording: false, phase: "idle",
      runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
      observedAtMilliseconds: 0, commandId: null, publicationPending: false,
      error: null, currentPatternId: null, pendingSwitch: null,
      ...overrides,
    },
  });
  const view = render(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={transport({playing: true})} onSelectPattern={onSelectPattern} />,
  );
  const slot = (name: string) => screen.getByRole("button", {name: new RegExp(`^${name}$`)});
  await userEvent.click(slot("Launch Pattern 1"));
  expect(onSelectPattern).toHaveBeenCalledExactlyOnceWith(ids.pattern1);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  // An empty slot launches nothing: no selection, no Performance launch.
  await userEvent.click(slot("Launch Pattern 3"));
  expect(onSelectPattern).toHaveBeenCalledTimes(1);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  // Stopped works the same way; the transport state decides the path in the app.
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={transport({playing: false})} onSelectPattern={onSelectPattern} />);
  await userEvent.click(slot("Launch Pattern 2"));
  expect(onSelectPattern).toHaveBeenLastCalledWith(ids.pattern2);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
});

// #1958: outside a Performance recording the slots follow the transport: a
// settling or recording transport keeps them closed, and so does a missing
// transport projection.
test("Launch without a Performance recording stays closed while the transport records or settles", async () => {
  const fixture = controllerFixture();
  const status = (overrides: Partial<PatternTransportStatus>): PatternTransportState => ({
    ...initialPatternTransportState,
    sessionId: "session-1",
    status: {
      engaged: true, playing: true, recording: false, phase: "idle",
      runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
      observedAtMilliseconds: 0, commandId: null, publicationPending: false,
      error: null, currentPatternId: null, pendingSwitch: null,
      ...overrides,
    },
  });
  const view = render(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={status({playing: true, recording: true})} onSelectPattern={vi.fn()} />);
  for (const name of ["Launch Pattern 1", "Launch Pattern 2", "Launch Pattern 3"]) {
    expect(screen.getByRole("button", {name: new RegExp(`^${name}$`)})
      .hasAttribute("disabled")).toBe(true);
  }
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={status({phase: "preparing"})} onSelectPattern={vi.fn()} />);
  expect(screen.getByRole("button", {name: /^Launch Pattern 1$/})
    .hasAttribute("disabled")).toBe(true);
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      onSelectPattern={vi.fn()} />);
  expect(screen.getByRole("button", {name: /^Launch Pattern 1$/})
    .hasAttribute("disabled")).toBe(true);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
});

test("Launch stays closed until Performance recording setup finishes", async () => {
  const fixture = controllerFixture();
  const begin = deferred<{performanceId: string; committedRevision: number;
    replayed: false; projectRevision: number}>();
  fixture.runtime.calls.begin.mockReturnValueOnce(begin.promise);
  const onSelectPattern = vi.fn();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    transport={idlePatternTransport()} onSelectPattern={onSelectPattern} />);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  let recording!: Promise<void>;
  act(() => { recording = fixture.controller.record(); });
  await waitFor(() => expect(fixture.runtime.calls.begin).toHaveBeenCalledOnce());
  expect(fixture.controller.getState().recording.phase).toBe("starting");
  const launch = screen.getByRole("button", {name: /^Launch Pattern 1$/});
  expect(launch.hasAttribute("disabled")).toBe(true);
  fireEvent.click(launch);
  expect(onSelectPattern).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  await act(async () => {
    begin.resolve({performanceId: ids.performance, committedRevision: 8,
      replayed: false, projectRevision: 8});
    await recording;
  });
  fireEvent.click(launch);
  await waitFor(() => expect(fixture.runtime.calls.launch).toHaveBeenCalledOnce());
  expect(onSelectPattern).not.toHaveBeenCalled();
  await act(() => fixture.controller.stop());
});

test("Launch stays closed until Performance capture stop settles", async () => {
  const fixture = controllerFixture();
  const captureStopped = deferred<void>();
  fixture.captureStop.mockImplementationOnce(() => captureStopped.promise);
  const onSelectPattern = vi.fn();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    transport={idlePatternTransport()} onSelectPattern={onSelectPattern} />);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  await act(() => fixture.controller.record());
  let stopping!: Promise<void>;
  act(() => { stopping = fixture.controller.stop(); });
  await waitFor(() => expect(fixture.captureStop).toHaveBeenCalledOnce());
  expect(fixture.controller.getState().recording.phase).toBe("stopping");
  const launch = screen.getByRole("button", {name: /^Launch Pattern 1$/});
  expect(launch.hasAttribute("disabled")).toBe(true);
  fireEvent.click(launch);
  expect(onSelectPattern).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  await act(async () => {
    captureStopped.resolve();
    await stopping;
  });
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  fireEvent.click(launch);
  expect(onSelectPattern).toHaveBeenCalledExactlyOnceWith(ids.pattern1);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
});

// #1958: with no Performance facts, the transport's pending switch marks its
// slot Queued and the playing Pattern marks its slot Playing.
test("slot states follow the transport's queued switch and playing Pattern", () => {
  const fixture = controllerFixture();
  render(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={{
        ...initialPatternTransportState,
        sessionId: "session-1",
        status: {
          engaged: true, playing: true, recording: false, phase: "idle",
          runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
          observedAtMilliseconds: 0, commandId: null, publicationPending: false,
          currentPatternId: ids.pattern1,
          pendingSwitch: {patternId: ids.pattern2, activationFrame: 96_000},
          error: null,
        },
      }} onSelectPattern={vi.fn()} />);
  expect(screen.getByRole("button", {name: /^Launch Pattern 1$/})
    .getAttribute("data-launch")).toBe("acknowledged");
  expect(screen.getByRole("button", {name: /^Launch Pattern 2$/})
    .getAttribute("data-launch")).toBe("pending");
  expect(screen.getByRole("button", {name: /^Launch Pattern 3$/})
    .getAttribute("data-launch")).toBe("idle");
  const group = screen.getByRole("button", {name: /^Pattern slots 1 to 4$/});
  expect(group.textContent).toContain("Queued");
  expect(group.textContent).toContain("Playing");
});

test("keeps the other five confirmed FX behind FX / MORE", async () => {
  renderSurface();
  const fx = screen.getByRole("region", {name: "Performance FX"});
  const more = within(fx).getByRole("button", {name: "FX / MORE"});
  expect(more.getAttribute("aria-expanded")).toBe("false");
  expect(within(fx).queryByRole("slider", {name: "Stutter"})).toBeNull();

  await userEvent.click(more);
  expect(more.getAttribute("aria-expanded")).toBe("true");
  expect(within(fx).getAllByRole("slider").map((slider) => slider.getAttribute("aria-label")))
    .toEqual(["Filter", "Delay", "Reverb", "Stutter", "Gate", "Reverse", "Crush", "Cutter"]);

  await userEvent.click(more);
  expect(within(fx).queryByRole("slider", {name: "Cutter"})).toBeNull();
});

test("projects the Host Bank without duplicate buttons or a Core request", () => {
  const rendered = renderSurface();
  const before = Object.values(rendered.fixture.runtime.calls)
    .reduce((count, call) => count + call.mock.calls.length, 0);
  rendered.rerender(1);
  expect(rendered.fixture.controller.getState().bank).toBe(1);
  expect(screen.queryByRole("group", {name: "Perform Bank"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Bank B"})).toBeNull();
  expect(Object.values(rendered.fixture.runtime.calls)
    .reduce((count, call) => count + call.mock.calls.length, 0)).toBe(before);
});

test.each([
  {captureState: "unconfigured" as const, message: null},
  {captureState: "configured" as const, message: "Preparing recording"},
  {captureState: "unavailable" as const,
    message: "Performance recording could not start. Reload the page and play a Pad to start audio, then record."},
])("gates Record for $captureState capture", ({captureState, message}) => {
  renderSurface(controllerFixture({captureState}));
  expect(screen.getByRole("button", {name: "Record Performance"}).hasAttribute("disabled"))
    .toBe(true);
  if (message === null) expect(screen.queryByText(/recording (unavailable|preparing)/i)).toBeNull();
  else expect(screen.getByText(message, {exact: false})).not.toBeNull();
});

test.each(["tap-initialization-failed", "tap-processor-failed"] as const)(
  "%s recovery names the musical audio-start gesture", (code) => {
    const fixture = controllerFixture({captureState: "unavailable"});
    fixture.runtime.setStatus(status("unavailable", code));
    renderSurface(fixture);
    expect(screen.getByText(
      "Performance recording could not start. Reload the page and play a Pad to start audio, then record.",
    )).not.toBeNull();
    expect(screen.getByRole("button", {name: "Record Performance"}).hasAttribute("disabled"))
      .toBe(true);
    expect(screen.queryByRole("button", {name: "Activate audio"})).toBeNull();
    expect(fixture.runtime.calls.begin).not.toHaveBeenCalled();
  },
);

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
  const reportFailure = vi.fn();
  const fixture = controllerFixture({reportFailure});
  fixture.captureStop.mockRejectedValueOnce(new Error("tap stop failed"));
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));

  fixture.getQueueListener()?.requestCaptureStop();

  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  // #1680: the raw message goes to diagnostics; the surface shows the catalogue.
  expect(fixture.controller.getState().error).toBe("Something went wrong in Creator. Try again. Details are in Developer diagnostics.");
  expect(reportFailure).toHaveBeenCalledWith("Perform",
    expect.objectContaining({message: "tap stop failed"}));
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
  expect(fixture.controller.getState().error).toMatch(/The interrupted recording is kept for recovery\.$/);
  expect(fixture.controller.getState().error).not.toMatch(/projection failed|discard failed/);
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

test("applies FX and HOLD live with no recording running and journals nothing", async () => {
  const {fixture} = renderSurface();
  const filter = screen.getByRole("slider", {name: "Filter"});
  expect(filter.hasAttribute("disabled")).toBe(false);
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "630"}});
  fireEvent.pointerUp(filter, {pointerId: 3});
  await waitFor(() => expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(3));
  expect(fixture.runtime.calls.fx.mock.calls.map(([event]) => event)).toEqual([
    {kind: "fx_engage", fx: "filter", value: 500},
    {kind: "fx_move", fx: "filter", value: 630},
    {kind: "fx_release", fx: "filter"},
  ]);
  expect(fixture.runtime.calls.raw).not.toHaveBeenCalled();

  const hold = screen.getByRole("button", {name: "HOLD"});
  expect(hold.hasAttribute("disabled")).toBe(false);
  await userEvent.click(hold);
  await waitFor(() => expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(4));
  expect(hold.getAttribute("aria-pressed")).toBe("true");
  await userEvent.click(hold);
  await waitFor(() => expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(5));
  expect(fixture.runtime.calls.fx.mock.calls.slice(3).map(([event]) => event))
    .toEqual([{kind: "hold_on"}, {kind: "hold_off"}]);
  expect(fixture.runtime.calls.raw).not.toHaveBeenCalled();
});

test("releases an open FX gesture when the pointer is cancelled", async () => {
  const {fixture} = renderSurface();
  const filter = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "640"}});
  fireEvent.pointerCancel(filter, {pointerId: 3});
  await waitFor(() => expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(3));
  expect(fixture.runtime.calls.fx.mock.calls.map(([event]) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_release"]);
});

test("journals already-engaged FX and HOLD when recording begins", async () => {
  const {fixture} = renderSurface();
  const filter = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "640"}});
  await userEvent.click(screen.getByRole("button", {name: "HOLD"}));
  await waitFor(() => expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(3));
  // Journaled hold_on makes Core's authority report HOLD on; the double
  // mirrors that instead of its neutral default.
  (fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>)
    .mockResolvedValue(authority({hold: true}));

  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(2));
  const journaled = fixture.runtime.calls.raw.mock.calls.map(([request]) => request.event);
  expect(journaled[0]).toEqual({kind: "hold_on"});
  expect(journaled[1]).toMatchObject({kind: "fx_engage", fx: "filter", value: 640});

  // The gesture is still open: lifting the fader releases it through the
  // journaled path (recording applies gestures live itself), and HOLD stays
  // on because recording is an independent toggle.
  fireEvent.pointerUp(filter, {pointerId: 3});
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(3));
  expect(fixture.runtime.calls.raw.mock.calls[2]?.[0].event)
    .toMatchObject({kind: "fx_release", fx: "filter"});
  expect(fixture.runtime.calls.fx.mock.calls.map(([event]) => event.kind))
    .toEqual(["fx_engage", "fx_move", "hold_on"]);
  expect(fixture.controller.getState().hold).toBe(true);
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
  // During recording the journaled path applies each gesture live, so the
  // session-free op stays silent and the gesture is applied exactly once.
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
});

test("releases an open FX gesture when FX / MORE collapses it away", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  const more = screen.getByRole("button", {name: "FX / MORE"});
  await userEvent.click(more);
  const stutter = screen.getByRole("slider", {name: "Stutter"});
  fireEvent.pointerDown(stutter, {pointerId: 5});
  fireEvent.change(stutter, {target: {value: "700"}});
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(2));

  // Collapsing unmounts the input, so the gesture cannot be closed by a later
  // pointerup on it; the bank has to close it or Core keeps it open forever.
  await userEvent.click(more);
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(3));
  const requests = fixture.runtime.calls.raw.mock.calls.map(([request]) => request);
  expect(requests.map(({event}) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_release"]);
  expect(requests[2]?.event).toMatchObject({fx: "stutter"});
});

test("keeps FX engaged across stop and re-journals them in the next recording", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "pad-old",
    slot: 0, velocity: 100});
  fixture.controller.engageFx("filter", 650);
  await fixture.controller.stop();
  const firstKinds = fixture.runtime.calls.raw.mock.calls.map(([request]) =>
    request.event.kind);
  // Stop closes Pad gestures; FX stay engaged because recording and FX are
  // independent toggles — Core closes the journaled FX chain itself.
  expect(firstKinds).toEqual(["pad_press", "fx_engage", "pad_release"]);
  expect(fixture.controller.getState().fx.filter).toBe(650);

  await fixture.controller.discard();
  await fixture.controller.record();
  await waitFor(() => expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(4));
  expect(fixture.runtime.calls.raw.mock.calls[3]?.[0].event)
    .toMatchObject({kind: "fx_engage", fx: "filter", value: 650});
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

test("the upper launch cue and local controls follow the same pending and acknowledged producer", async () => {
  const fixture = controllerFixture();
  const query = fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>;
  query.mockResolvedValueOnce(authority({
    pendingLaunch: {requestId: "event-1", patternSlot: 0, targetTick: 1920, claimed: false},
  }));
  renderSurface(fixture);
  render(<PerformOverview state={creatorState()} controller={fixture.controller} />);
  const slot = () => screen.getByRole("button", {name: "Launch Pattern 1"});
  const cue = () => screen.getByLabelText("Pattern launch cue").textContent;
  expect(slot().textContent).not.toMatch(/Queued|Playing/);
  expect(cue()).toBe("LAST LAUNCH — · NOTHING QUEUED");

  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(slot());
  await waitFor(() => expect(slot().textContent).toMatch(/Queued/));
  expect(slot().getAttribute("data-launch")).toBe("pending");
  expect(cue()).toBe("LAST LAUNCH — → QUEUED SLOT 01");
  await userEvent.click(screen.getByRole("button", {name: "Pattern slots 13 to 16"}));
  expect(screen.getByRole("button", {name: "Pattern slots 1 to 4"}).textContent).toContain("Queued");
  expect(screen.queryByRole("button", {name: "Launch Pattern 1"})).toBeNull();

  query.mockResolvedValueOnce(authority({journalRevision: 2,
    lastLaunchAck: {requestId: "event-1", patternSlot: 0, effectiveTick: 1920}}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Pattern slots 1 to 4"}).textContent).toContain("Playing"));
  await userEvent.click(screen.getByRole("button", {name: "Pattern slots 1 to 4"}));
  await waitFor(() => expect(slot().textContent).toMatch(/Playing/));
  expect(slot().getAttribute("data-launch")).toBe("acknowledged");
  expect(cue()).toBe("ACKNOWLEDGED SLOT 01 · NOTHING QUEUED");
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
  selectPerformPage("Slots");
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
  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Flush Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  expect(fixture.order.slice(-3)).toEqual(["core-stop", "capture-stop", "tail-drained"]);
  selectPerformPage("Takes");
  await userEvent.clear(screen.getByRole("textbox", {name: "Performance name"}));
  await userEvent.type(screen.getByRole("textbox", {name: "Performance name"}), "Night Set");
  selectPerformPage("Takes");
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

  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toMatch(/Project is busy.*retry Save Performance/i));
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  expect(screen.getByRole("button", {name: "Save Performance"})
    .hasAttribute("disabled")).toBe(false);
  expect(fixture.store.bind).not.toHaveBeenCalled();

  selectPerformPage("Takes");
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
  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Retry WAV bind"}))
    .not.toBeNull());

  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert").textContent).toBe("The recording could not be saved into the Project. Choose Retry WAV bind.");
  selectPerformPage("Takes");
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
  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toBe("The Performance was saved, but Creator could not show the latest Project. Choose Save Performance again."));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.store.bind).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.phase).toBe("stopped");

  selectPerformPage("Takes");
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

  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toBe("The Performance was saved, but Creator could not show the latest Project. Choose Save Performance again."));
  expect(fixture.runtime.session.savePerformance).toHaveBeenCalledTimes(1);
  expect(fixture.store.bind).not.toHaveBeenCalled();

  selectPerformPage("Takes");
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
  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Retry WAV bind"}))
    .not.toBeNull());
  expect(fixture.store.bind).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");

  selectPerformPage("Takes");
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
  selectPerformPage("Takes");
  await userEvent.clear(screen.getByRole("textbox", {name: "Performance name"}));
  await userEvent.type(screen.getByRole("textbox", {name: "Performance name"}), "Lost Reply");
  selectPerformPage("Takes");
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
  selectPerformPage("Takes");
  await userEvent.click(screen.getByRole("button", {name: "Discard Performance"}));
  await waitFor(() => expect(fixture.store.discard).toHaveBeenCalledTimes(1));
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  expect(screen.getByRole("alert").textContent).toBe("The Performance was discarded, but Creator could not show the latest Project. Choose Discard Performance again.");

  selectPerformPage("Takes");
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

  selectPerformPage("Replay");
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
  expect(fixture.controller.getState().resampleStatus).toContain("committed · Pad B01");
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
  selectPerformPage("Replay");
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
  selectPerformPage("Replay");
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

test("a replay poll reply that outlives Stop Replay cannot overwrite the terminal state", async () => {
  const fixture = controllerFixture();
  const session = fixture.runtime.session;
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing",
      resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      projectRevision: null});
  (session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", requestId: "stop-replay",
      state: "stopped", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      replayed: false, projectRevision: null});
  // The poll answers only when the test says so: this reply carries the
  // pre-stop state and lands after the terminal transition (#746).
  const pendingPolls: ((status: unknown) => void)[] = [];
  (session.queryPerformanceReplayStatus as ReturnType<typeof vi.fn>)
    .mockImplementation(() => new Promise((resolve) => {
      pendingPolls.push(resolve);
    }));

  await fixture.controller.beginReplay(ids.performance);
  void fixture.controller.refreshReplay();
  expect(pendingPolls.length).toBe(1);
  await fixture.controller.stopReplay();
  expect(fixture.controller.getState().replay?.state).toBe("stopped");
  expect(fixture.controller.getState().replayNeutral).toBe(true);

  for (const answer of pendingPolls) {
    answer({replayId: "replay-1", state: "playing", resolvedRevision: 7,
      eventCursor: 0, eventCount: 4, projectRevision: null});
  }
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(fixture.controller.getState().replay?.state).toBe("stopped");
  expect(fixture.controller.getState().replayNeutral).toBe(true);
});

test("a current replay poll reply still refreshes the playing state", async () => {
  const fixture = controllerFixture();
  const session = fixture.runtime.session;
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockResolvedValue({replayId: "replay-1", state: "playing",
      resolvedRevision: 7, eventCursor: 0, eventCount: 4,
      projectRevision: null});
  const pendingPolls: ((status: unknown) => void)[] = [];
  (session.queryPerformanceReplayStatus as ReturnType<typeof vi.fn>)
    .mockImplementation(() => new Promise((resolve) => {
      pendingPolls.push(resolve);
    }));

  await fixture.controller.beginReplay(ids.performance);
  const poll = fixture.controller.refreshReplay();
  for (const answer of pendingPolls) {
    answer({replayId: "replay-1", state: "playing", resolvedRevision: 8,
      eventCursor: 1, eventCount: 4, projectRevision: null});
  }
  await poll;
  expect(fixture.controller.getState().replay?.resolvedRevision).toBe(8);
});

test("refuses to leave while replay neutral reset remains pending", async () => {
  const fixture = controllerFixture({maximumStatusQueries: 2,
    waitForStatusQuery: async () => {}});
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  fixture.controller.togglePadGate("solo", 63);
  await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
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
  expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind))
    .toEqual(["pad_solo"]);
  expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]);
});

test("renders saved replay after moving resampling to empty Pad capture", async () => {
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
  selectPerformPage("Replay");
  await userEvent.click(await screen.findByRole("button", {name: "Replay Take 1"}));
  expect(screen.getByRole("status", {name: "Replay status"}).textContent).toContain("playing");
  expect(screen.queryByRole("spinbutton", {name: "Resample start frame"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Resample selection"})).toBeNull();
  expect(screen.getByRole("button", {name: "Stop Replay"})).toBeTruthy();
});

test("discards the stopped WAV through the store and refreshes Project truth", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1));
  selectPerformPage("Takes");
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

test("another recording owner disables Perform Record before acquiring its master tap", async () => {
  const fixture = controllerFixture();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    recordingBusy />);
  const record = screen.getByRole("button", {name:"Record Performance"});
  expect((record as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(record);
  expect(fixture.controller.getState().recording.phase).toBe("idle");
});


test("Slots retains assignment choices across pages without mutating Truth", async () => {
  const {fixture} = renderSurface();
  expect(screen.getAllByRole("button", {name: /^Launch Pattern /})).toHaveLength(4);
  expect(screen.queryByRole("combobox", {name: "Pattern assignment"})).toBeNull();
  expect(screen.queryByRole("textbox", {name: "Performance name"})).toBeNull();
  selectPerformPage("Slots");
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Pattern slot"}),
    within(screen.getByRole("combobox", {name: "Pattern slot"})).getByRole("option", {name: "16"}));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Pattern assignment"}), ids.pattern2);
  selectPerformPage("Takes");
  selectPerformPage("Slots");
  expect((screen.getByRole("combobox", {name: "Pattern slot"}) as HTMLSelectElement).value).toBe("15");
  expect((screen.getByRole("combobox", {name: "Pattern assignment"}) as HTMLSelectElement).value).toBe(ids.pattern2);
  expect(fixture.runtime.session.assignPatternSlot).not.toHaveBeenCalled();
  selectPerformPage("Live");
  expect(screen.getAllByRole("button", {name: /^Launch Pattern /})).toHaveLength(4);
});

test("subpages retain the recording and HOLD until explicit Stop", async () => {
  const {fixture} = renderSurface();
  expect(screen.queryByRole("button", {name: "Stop Performance"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  (fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>)
    .mockResolvedValue(authority({hold: true}));
  await userEvent.click(screen.getByRole("button", {name: "HOLD"}));
  const session = fixture.controller.getState().recording.sessionId;
  expect(session).not.toBeNull();
  expect(screen.queryByRole("button", {name: "Record Performance"})).toBeNull();
  for (const name of ["Slots", "Takes", "Replay", "Live"] as const) {
    selectPerformPage(name);
    expect(fixture.controller.getState().recording.sessionId).toBe(session);
    expect(fixture.controller.getState().recording.phase).toBe("recording");
    expect(fixture.controller.getState().hold).toBe(true);
  }
  expect(fixture.runtime.calls.begin).toHaveBeenCalledTimes(1);
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  expect(fixture.captureStop).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await userEvent.click(await screen.findByRole("button", {name: "Review recording"}));
  await userEvent.clear(screen.getByRole("textbox", {name: "Performance name"}));
  await userEvent.type(screen.getByRole("textbox", {name: "Performance name"}), "Retained take");
  selectPerformPage("Replay");
  selectPerformPage("Takes");
  expect((screen.getByRole("textbox", {name: "Performance name"}) as HTMLInputElement).value).toBe("Retained take");
  expect(screen.getByRole("button", {name: "Save Performance"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Discard Performance"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Export Performance WAV"})).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Stop Performance"})).toBeNull();
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
});

test("page navigation waits for an FX gesture and keeps More FX expansion", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  const filter = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(filter, {pointerId: 41});
  fireEvent.change(filter, {target: {value: "650"}});
  const pages = within(screen.getByRole("navigation", {name: "Perform pages"}));
  expect(pages.getAllByRole("button").every(button => (button as HTMLButtonElement).disabled)).toBe(true);
  selectPerformPage("Slots");
  expect(pages.getByRole("button", {name: "Live"}).getAttribute("aria-current")).toBe("page");
  fireEvent.pointerUp(filter, {pointerId: 41});
  fireEvent.lostPointerCapture(filter, {pointerId: 41});
  await waitFor(() => expect(fixture.runtime.calls.fx.mock.calls.map(([event]) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_release"]));
  expect(pages.getAllByRole("button").every(button => !(button as HTMLButtonElement).disabled)).toBe(true);
  selectPerformPage("Slots");
  selectPerformPage("Live");
  expect(screen.getByRole("button", {name: "FX / MORE"}).getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("slider", {name: "Reverb"})).toBeTruthy();
  // Component events fix one release; packaged native pointer capture covers
  // drag-off delivery, which jsdom cannot establish.
});

test("Replay keeps playing and polling while another subpage is visible", async () => {
  const fixture = controllerFixture();
  const session = fixture.runtime.session;
  (session.listPerformances as ReturnType<typeof vi.fn>).mockResolvedValue([
    {performanceId: ids.performance, name: "Take 1", createdBpm: 120,
      recordingArtifact: null, eventCount: 4},
  ]);
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>).mockResolvedValue({
    replayId: "replay-1", state: "playing", resolvedRevision: 7,
    eventCursor: 0, eventCount: 4, projectRevision: null,
  });
  (session.stopPerformanceReplay as ReturnType<typeof vi.fn>).mockResolvedValue({
    replayId: "replay-1", requestId: "stop-replay", state: "stopped", resolvedRevision: 7,
    eventCursor: 0, eventCount: 4, replayed: false, projectRevision: null,
  });
  renderSurface(fixture);
  selectPerformPage("Replay");
  await userEvent.click(await screen.findByRole("button", {name: "Replay Take 1"}));
  selectPerformPage("Slots");
  expect(fixture.controller.getState().replay?.state).toBe("playing");
  expect(session.stopPerformanceReplay).not.toHaveBeenCalled();
  await waitFor(() => expect(session.queryPerformanceReplayStatus).toHaveBeenCalled());
  selectPerformPage("Replay");
  expect(screen.getByRole("status", {name: "Replay status"}).textContent).toContain("playing");
  await userEvent.click(screen.getByRole("button", {name: "Stop Replay"}));
  expect(session.stopPerformanceReplay).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("status", {name: "Replay status"}).textContent).toContain("stopped");
});


test("launch groups keep all sixteen addresses and the selected group across pages", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  const labels: string[] = [];
  for (const first of [1, 5, 9, 13]) {
    await userEvent.click(screen.getByRole("button", {name: `Pattern slots ${first} to ${first + 3}`}));
    const slots = screen.getAllByRole("button", {name: /^Launch Pattern /});
    expect(slots).toHaveLength(4);
    labels.push(...slots.map(slot => slot.getAttribute("aria-label")!));
    for (const slot of slots) await userEvent.click(slot);
  }
  expect(labels).toEqual(Array.from({length: 16}, (_, index) => `Launch Pattern ${index + 1}`));
  expect(fixture.runtime.calls.launch.mock.calls.map(([request]) => request.patternSlot))
    .toEqual(Array.from({length: 16}, (_, index) => index));
  selectPerformPage("Slots");
  selectPerformPage("Live");
  expect(screen.getByRole("button", {name: "Pattern slots 13 to 16"}).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("button", {name: "Launch Pattern 16"})).toBeTruthy();
});


test("returning from System opens the retained recording review without reconnecting it", async () => {
  const fixture = controllerFixture();
  const onReviewShown = vi.fn();
  const props = {controller: fixture.controller, project, bank: 0 as const, onReviewShown};
  const view = render(<PerformSurface {...props} />);
  await userEvent.click(await screen.findByRole("button", {name: "Record Performance"}));
  await userEvent.click(await screen.findByRole("button", {name: "Stop Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  const beginCalls = fixture.runtime.calls.begin.mock.calls.length;
  view.rerender(<PerformSurface {...props} reviewRequested />);
  expect(screen.getByRole("button", {name: "Save Performance"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Discard Performance"})).toBeTruthy();
  expect(onReviewShown).toHaveBeenCalledTimes(1);
  expect(fixture.runtime.calls.begin).toHaveBeenCalledTimes(beginCalls);
  await userEvent.click(screen.getByRole("button", {name: "Discard Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("idle"));
});

test("Perform encoder groups retain their effect values across group switches and rest", async () => {
  const fixture = controllerFixture();
  let current: ContextualEncoders | null = null;
  const bind = (value: ContextualEncoders | null) => {current = value;};
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={bind} />);
  expect(Object.values(current!.bindings).map((binding) => binding.label)).toEqual(["Filter", "Delay", "Reverb"]);
  act(() => current!.bindings[1]!.onTurn(1, true));
  expect(fixture.controller.getState().fx.filter).toBe(501);
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  expect(Object.values(current!.bindings).map((binding) => binding.label)).toEqual(["Crush", "Stutter", "Gate"]);
  act(() => current!.bindings[1]!.onTurn(2));
  expect(fixture.controller.getState().fx.crush).toBe(520);
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  expect(fixture.controller.getState().fx).toMatchObject({filter: 501, crush: 520});
  for (const page of ["Slots", "Takes", "Replay", "Live"] as const) {
    selectPerformPage(page);
    expect(Object.values(current!.bindings).map((binding) => binding.label)).toEqual(["Filter", "Delay", "Reverb"]);
    expect(fixture.controller.getState().fx).toMatchObject({filter: 501, crush: 520});
    expect(fixture.runtime.calls.fx.mock.calls.some(([event]) => event.kind === "fx_release")).toBe(false);
  }
  expect(fixture.runtime.calls.fx.mock.calls.some(([event]) => event.kind === "fx_release")).toBe(false);
});

test.each([false, true])("leaving Perform releases rotary gestures with HOLD=%s", async (hold) => {
  const fixture = controllerFixture();
  if (hold) fixture.controller.toggleHold();
  fixture.controller.turnFx("delay", 2);
  await fixture.controller.leave();
  expect(fixture.runtime.calls.fx).toHaveBeenLastCalledWith({kind: "fx_release", fx: "delay"});
  expect(fixture.controller.getState().fx.delay).toBe(hold ? 520 : 500);
});

test("a rotary takeover of a touch gesture journals one matching release before stop", async () => {
  const fixture = controllerFixture();
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  const id = fixture.controller.engageFx("reverb", 650);
  fixture.controller.turnFx("reverb", 1, true);
  fixture.controller.releaseFx(id, "reverb");
  await fixture.controller.leave();
  const events = fixture.runtime.calls.raw.mock.calls.map(([request]) => request.event)
    .filter((event) => event.fx === "reverb");
  expect(events.map((event) => event.kind)).toEqual(["fx_engage", "fx_move", "fx_release"]);
  expect(events.every((event) => event.gestureId === id)).toBe(true);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
});

test("touch continues a rotary FX gesture until page exit journals its matching release", async () => {
  const fixture = controllerFixture();
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  fixture.controller.turnFx("reverb", 1);
  const id = fixture.controller.engageFx("reverb", 650);
  fixture.controller.moveFx(id, "reverb", 651);
  fixture.controller.releaseFx(id, "reverb");
  expect(fixture.controller.getState().fx.reverb).toBe(651);
  await fixture.controller.leave();
  const events = fixture.runtime.calls.raw.mock.calls.map(([request]) => request.event)
    .filter((event) => event.fx === "reverb");
  expect(events.map((event) => event.kind)).toEqual([
    "fx_engage", "fx_move", "fx_move", "fx_release",
  ]);
  expect(events.every((event) => event.gestureId === id)).toBe(true);
  expect(fixture.controller.getState().fx.reverb).toBe(500);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
});

// ---------------------------------------------------------------------------
// C1 typed independent Filter and live-control consumer oracles.
// ---------------------------------------------------------------------------

// A typed producer double updates its own readback. A receipt alone must never
// turn the controller's optimistic value into a Core fact.
function enableTypedCore(calls: ReturnType<typeof sessionFixture>["calls"]) {
  let applied = liveState();
  let sequence = "0";
  const apply = calls.liveControl.getMockImplementation()!;
  const updateMaskAndFx = (intent: Record<string, unknown>) => {
    if (intent.kind === "filter_parameter") {
      const field = {type: "type", cutoff_hz: "cutoffHz",
        resonance_milli: "resonanceMilli"}[intent.parameter as string];
      applied = {...applied, filter: {...applied.filter,
        [field!]: intent.value, engaged: true, frozen: false}};
    } else if (intent.kind === "filter_release") {
      applied = {...applied, filter: {...applied.filter,
        engaged: false, frozen: applied.hold}};
    } else if (intent.kind === "fx_parameter" || intent.kind === "fx_release") {
      const fx = intent.fx as keyof typeof applied.otherFx;
      applied = {...applied, otherFx: {...applied.otherFx,
        [fx]: intent.kind === "fx_parameter"
          ? {value: intent.value, engaged: true, frozen: false}
          : {...applied.otherFx[fx], engaged: false, frozen: applied.hold,
              value: applied.hold ? applied.otherFx[fx].value : 0}}};
    } else if (intent.kind === "pad_mute" || intent.kind === "pad_solo") {
      const field = intent.kind === "pad_mute" ? "mutedSlots" : "soloSlots";
      const slots = new Set(applied[field]);
      if (intent.enabled) slots.add(intent.slot as number);
      else slots.delete(intent.slot as number);
      applied = {...applied, [field]: [...slots].sort((a, b) => a - b)};
    } else if (intent.kind === "clear_pad_gates") {
      applied = {...applied, mutedSlots: [], soloSlots: []};
    } else if (intent.kind === "hold_on" || intent.kind === "hold_off") {
      applied = {...applied, hold: intent.kind === "hold_on"};
    }
  };
  calls.liveControl.mockImplementation(async (request) => {
    const receipt = await apply(request);
    sequence = receipt.controlSequence;
    updateMaskAndFx(request.intent);
    return receipt;
  });
  const raw = calls.raw.getMockImplementation()!;
  calls.raw.mockImplementation(async (request) => {
    const receipt = await raw(request);
    if (["pad_mute", "pad_solo", "clear_pad_gates"].includes(String(request.event.kind))) {
      updateMaskAndFx(request.event);
    }
    return receipt;
  });
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: applied, applied,
    acceptedControlSequence: sequence, appliedControlSequence: sequence,
  }));
}

function headeredBegin(fxBindings: readonly Record<string, unknown>[] = []) {
  return async (request?: Record<string, unknown>) => ({
    performanceId: ids.performance, committedRevision: 8, replayed: false,
    projectRevision: 8, profile: "header_input_sequence" as const,
    controlEpoch: typeof request?.controlEpoch === "string"
      ? request.controlEpoch : LIVE_EPOCH,
    coreControlReady: true, nextRecordingSequence: "0", fxBindings,
  });
}

test("typed Filter state reads back from Core: OFF, LP, 20 kHz, 0%", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  expect(fixture.controller.getState().filter).toMatchObject({
    type: "lp", cutoffHz: 20000, resonanceMilli: 0,
    engaged: false, frozen: false, provenance: "core",
  });
  // The main group's first fader keeps its legacy slot and name; the typed
  // change is the readback — Core Hz, never a percentage-derived guess.
  expect(screen.getByRole("slider", {name: "Filter"})).toBeTruthy();
  expect(screen.getByText("20.0 kHz")).toBeTruthy();
});

test("a Filter ACK stays pending until the applied Core tuple is read back", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const applied = deferred<ReturnType<typeof liveStatusAvailable>>();
  calls.liveStatus.mockImplementationOnce(() => applied.promise);
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(2));
  expect(fixture.controller.getState().filter.provenance).toBe("pending");
  const core = liveState({filter: {mode: "independent", type: "hp",
    cutoffHz: 18000, resonanceMilli: 123, engaged: true, frozen: false}});
  applied.resolve(liveStatusAvailable({accepted: core, applied: core,
    acceptedControlSequence: "1", appliedControlSequence: "1"}));
  await waitFor(() => expect(fixture.controller.getState().filter).toMatchObject({
    type: "hp", cutoffHz: 18000, resonanceMilli: 123, provenance: "core",
  }));
});

test("an older live-status response cannot overwrite a later Filter turn", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const oldStatus = deferred<ReturnType<typeof liveStatusAvailable>>();
  calls.liveStatus.mockImplementationOnce(() => oldStatus.promise);
  const oldRead = fixture.controller.refreshLiveStatus();
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(fixture.controller.getState().filter.provenance).toBe("core"));
  expect(fixture.controller.getState().filter.cutoffHz).toBe(cutoffPositionToHz(990));
  oldStatus.resolve(liveStatusAvailable());
  await oldRead;
  expect(fixture.controller.getState().filter.cutoffHz).toBe(cutoffPositionToHz(990));
});

test("a delayed Filter read cannot overwrite a later HOLD and HOLD reads applied Core state", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const delayed = deferred<ReturnType<typeof liveStatusAvailable>>();
  calls.liveStatus.mockImplementationOnce(() => delayed.promise);
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(2));
  fixture.controller.toggleHold();
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(2));
  const current = liveState({filter: {mode: "independent", type: "lp",
    cutoffHz: cutoffPositionToHz(990), resonanceMilli: 0, engaged: true, frozen: false}});
  delayed.resolve(liveStatusAvailable({accepted: current, applied: current,
    acceptedControlSequence: "1", appliedControlSequence: "1"}));
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(3));
  expect(fixture.controller.getState().hold).toBe(true);
  expect(fixture.controller.getState().filter.provenance).toBe("core");
});

test("an old recording-status read cannot clear a later admitted HOLD", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const old = deferred<ReturnType<typeof authority>>();
  const query = fixture.runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>;
  query.mockImplementationOnce(() => old.promise).mockResolvedValue(authority({hold: true}));
  const oldRead = fixture.controller.refreshAuthority();
  fixture.controller.toggleHold();
  await waitFor(() => expect(fixture.controller.getState().authority?.hold).toBe(true));
  old.resolve(authority({hold: false}));
  await oldRead;
  expect(fixture.controller.getState().authority?.hold).toBe(true);
  await fixture.controller.stop();
});

test("a late Filter ACK cannot adopt an old epoch's generation", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const oldAck = deferred<void>();
  const apply = calls.liveControl.getMockImplementation()!;
  calls.liveControl.mockImplementationOnce(async (request) => {
    const result = await apply(request);
    await oldAck.promise;
    return result;
  });
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(1));
  const newEpoch = "ffffffff-ffff-4fff-8fff-ffffffffffff";
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    controlEpoch: newEpoch, acceptedControlSequence: "2", appliedControlSequence: "2",
  }));
  await fixture.controller.refreshLiveStatus();
  oldAck.resolve();
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(2));
  expect(calls.liveControl.mock.calls[1]?.[0]).toMatchObject({
    controlEpoch: newEpoch, intent: {phase: "engage"},
  });
  expect(calls.liveControl.mock.calls[1]?.[0].intent.gestureGeneration).toBeUndefined();
});

test("changing only Filter type owns a gesture that page exit releases", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  fixture.controller.setFilterType("hp");
  await waitFor(() => expect(fixture.controller.getState().filter.provenance).toBe("core"));
  await fixture.controller.leave();
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(2));
  expect(calls.liveControl.mock.calls[1]?.[0].intent).toEqual({
    kind: "filter_release", gestureGeneration: "generation-1",
  });
});

test("Filter overflow is explicit and preserves the admitted move and matching release", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const first = deferred<void>();
  const apply = calls.liveControl.getMockImplementation()!;
  calls.liveControl.mockImplementationOnce(async (request) => {
    await first.promise;
    return apply(request);
  });
  const token = fixture.controller.touchFilterEngage("cutoff");
  fixture.controller.touchFilterMove(token, "cutoff", 700);
  fixture.controller.touchFilterMove(token, "cutoff", 600);
  fixture.controller.touchFilterRelease(token, "cutoff");
  await waitFor(() => expect(fixture.controller.getState().error).not.toBeNull());
  expect(calls.liveControl).toHaveBeenCalledTimes(1);
  first.resolve();
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(3));
  expect(calls.liveControl.mock.calls.map(([request]) => request.intent)).toEqual([
    {kind: "filter_parameter", phase: "engage", parameter: "cutoff_hz", value: 20000},
    {kind: "filter_parameter", phase: "move", parameter: "cutoff_hz",
      value: cutoffPositionToHz(700), gestureGeneration: "generation-1"},
    {kind: "filter_release", gestureGeneration: "generation-1"},
  ]);
  await waitFor(() => expect(fixture.controller.getState().filter).toMatchObject({
    cutoffHz: cutoffPositionToHz(700), engaged: false, provenance: "core",
  }));
});

test("typed Pad reservations stay bounded until matching releases finish", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const first = deferred<void>();
  const raw = calls.raw.getMockImplementation()!;
  calls.raw.mockImplementationOnce(async request => { await first.promise; return raw(request); });
  const pending: Promise<void>[] = [];
  for (let slot = 0; slot < 64; slot += 1) {
    pending.push(fixture.controller.recordRawEvent({kind: "pad_press",
      gestureId: `pad-${slot}`, slot, velocity: 100}));
    pending.push(fixture.controller.recordRawEvent({kind: "pad_release",
      gestureId: `pad-${slot}`, slot}));
  }
  const overflow = fixture.controller.recordRawEvent({kind: "pad_press",
    gestureId: "pad-65", slot: 0, velocity: 100});
  const observed = overflow.then(() => "accepted", error => String(error));
  // Release submission does not free its reserved slot while Core is stalled.
  await expect(observed).resolves.toMatch(/Too many open Pad gestures/);
  first.resolve();
  await Promise.all(pending);
  expect(calls.raw).toHaveBeenCalledTimes(128);
  expect(calls.raw.mock.calls.filter(([request]) => request.event.kind === "pad_release"))
    .toHaveLength(64);
  await fixture.controller.recordRawEvent({kind: "pad_press",
    gestureId: "pad-after-drain", slot: 0, velocity: 100});
  expect(calls.raw).toHaveBeenCalledTimes(129);
  await fixture.controller.stop();
});

test("Stop cancels a waiting typed move but finishes the admitted gesture release", async () => {
  const reportFailure = vi.fn();
  const fixture = controllerFixture({reportFailure});
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const first = deferred<void>();
  calls.raw.mockImplementation(async ({eventId, event}) => {
    if (event.phase === "engage") await first.promise;
    return {eventId, gestureGeneration: "recorded-generation",
      recordingGestureId: "recorded-filter", replayed: false};
  });
  const token = fixture.controller.touchFilterEngage("cutoff");
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
  fixture.controller.touchFilterMove(token, "cutoff", 700);
  fixture.controller.touchFilterRelease(token, "cutoff");
  const stopped = fixture.controller.stop();
  first.resolve();
  await stopped;
  expect(calls.raw.mock.calls.map(([request]) => request.event.kind)).toEqual([
    "filter_parameter", "filter_release",
  ]);
  expect(reportFailure).toHaveBeenCalledWith("Perform", expect.objectContaining({
    code: "HOST_STATE_INVALID", message: "Live input was cancelled before Core admission",
  }));
  expect(calls.stop).toHaveBeenCalledTimes(1);
});

test("begin-pending Filter inputs wait for both ACKs and dequeue against the Core mapping", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  const begin = deferred<void>();
  calls.begin.mockImplementation(async (request) => {
    await begin.promise;
    return headeredBegin([{fx: "filter", gestureGeneration: "start-generation",
      recordingGestureId: "start-filter"}])(request);
  });
  const capture = deferred<void>();
  calls.capture.mockImplementation(async (sink: {onStopped(): void}) => {
    await capture.promise;
    return {stop: vi.fn(async () => sink.onStopped())};
  });
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  const starting = fixture.controller.record();
  await waitFor(() => expect(calls.begin).toHaveBeenCalledTimes(1));
  fixture.controller.setFilterType("hp");
  fixture.controller.turnFilterCutoff(-1);
  expect(calls.raw).not.toHaveBeenCalled();
  expect(calls.liveControl).not.toHaveBeenCalled();
  begin.resolve();
  await waitFor(() => expect(calls.capture).toHaveBeenCalledTimes(1));
  expect(calls.raw).not.toHaveBeenCalled();
  capture.resolve();
  await starting;
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(2));
  expect(calls.raw.mock.calls.map(([request]) => request.event)).toEqual([
    {kind: "filter_parameter", phase: "move", parameter: "type", value: "hp",
      gestureId: "start-filter", gestureGeneration: "start-generation"},
    {kind: "filter_parameter", phase: "move", parameter: "cutoff_hz",
      value: cutoffPositionToHz(990), gestureId: "start-filter",
      gestureGeneration: "start-generation"},
  ]);
  expect(calls.liveControl).not.toHaveBeenCalled();
});

test("FILTER group maps Type/Cutoff/Resonance and entering it calls no producer", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={(value) => { current = value; }} />);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Cutoff", "Delay", "Reverb"]);
  fixture.runtime.calls.liveControl.mockClear();
  fixture.runtime.calls.liveStatus.mockClear();
  // Entering the group is pure UI state: no control and not even a status
  // query, and no audible enable.
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Type", "Cutoff", "Resonance"]);
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.liveStatus).not.toHaveBeenCalled();
  expect(fixture.controller.getState().filter.engaged).toBe(false);
  // The MORE group is preserved.
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Crush", "Stutter", "Gate"]);
});

test("Cutoff rotary walks the log range with exact endpoints and SHIFT fine steps", async () => {
  expect(cutoffPositionToHz(0)).toBe(20);
  expect(cutoffPositionToHz(1000)).toBe(20000);
  expect(cutoffHzToPosition(20)).toBe(0);
  expect(cutoffHzToPosition(20000)).toBe(1000);
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={(value) => { current = value; }} />);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  // SHIFT fine: one position below the 20 kHz rest engages the gesture.
  act(() => current!.bindings[1]!.onTurn(-1, true));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(1));
  expect(fixture.controller.getState().filter.cutoffHz)
    .toBe(cutoffPositionToHz(999));
  expect(fixture.runtime.calls.liveControl.mock.calls[0]?.[0]).toMatchObject({
    controlEpoch: LIVE_EPOCH,
    intent: {kind: "filter_parameter", phase: "engage", parameter: "cutoff_hz",
      value: cutoffPositionToHz(999)},
  });
  await waitFor(() =>
    expect(fixture.controller.getState().filter.provenance).toBe("core"));
  // Coarse: ±10 positions per detent, moving on the Core-issued generation.
  act(() => current!.bindings[1]!.onTurn(-1));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(2));
  expect(fixture.controller.getState().filter.cutoffHz)
    .toBe(cutoffPositionToHz(989));
  expect(fixture.runtime.calls.liveControl.mock.calls[1]?.[0].intent)
    .toMatchObject({kind: "filter_parameter", phase: "move",
      parameter: "cutoff_hz", value: cutoffPositionToHz(989),
      gestureGeneration: "generation-1"});
  // The bottom endpoint clamps exactly at 20 Hz.
  act(() => current!.bindings[1]!.onTurn(-200));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(3));
  expect(fixture.controller.getState().filter.cutoffHz).toBe(20);
});

test("FILTER ENC1 cycles the type and engages on the first actual change", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={(value) => { current = value; }} />);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  act(() => current!.bindings[1]!.onTurn(1));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(1));
  expect(fixture.controller.getState().filter.type).toBe("hp");
  expect(fixture.runtime.calls.liveControl.mock.calls[0]?.[0].intent)
    .toMatchObject({kind: "filter_parameter", phase: "engage",
      parameter: "type", value: "hp"});
  act(() => current!.bindings[1]!.onTurn(1));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(2));
  expect(fixture.controller.getState().filter.type).toBe("bp");
  expect(fixture.runtime.calls.liveControl.mock.calls[1]?.[0].intent)
    .toMatchObject({kind: "filter_parameter", phase: "move",
      parameter: "type", value: "bp", gestureGeneration: "generation-1"});
  // The wrap-around keeps cycling without a new engage.
  act(() => current!.bindings[1]!.onTurn(1));
  await waitFor(() =>
    expect(fixture.controller.getState().filter.type).toBe("lp"));
});

test("Cutoff touch keeps the pointer lifecycle with the Core generation", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  const cutoff = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(cutoff, {pointerId: 3});
  expect(fixture.controller.getState().filter.provenance).toBe("pending");
  fireEvent.change(cutoff, {target: {value: "500"}});
  fireEvent.pointerUp(cutoff, {pointerId: 3});
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(3));
  const intents = fixture.runtime.calls.liveControl.mock.calls
    .map(([request]) => request.intent);
  // Touch-down engages at the current value: entering changes no sound.
  expect(intents[0]).toMatchObject({kind: "filter_parameter", phase: "engage",
    parameter: "cutoff_hz", value: 20000});
  expect(intents[1]).toMatchObject({kind: "filter_parameter", phase: "move",
    parameter: "cutoff_hz", value: cutoffPositionToHz(500),
    gestureGeneration: "generation-1"});
  expect(intents[2]).toEqual({kind: "filter_release",
    gestureGeneration: "generation-1"});
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
  expect(fixture.controller.getState().filter.engaged).toBe(false);
});

test("Cutoff pointer cancel releases exactly like pointer-up", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  const cutoff = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(cutoff, {pointerId: 3});
  fireEvent.change(cutoff, {target: {value: "640"}});
  fireEvent.pointerCancel(cutoff, {pointerId: 3});
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(3));
  const kinds = fixture.runtime.calls.liveControl.mock.calls
    .map(([request]) => request.intent.kind);
  expect(kinds).toEqual(["filter_parameter", "filter_parameter", "filter_release"]);
});

test("rotary rest and group switches keep the Filter gesture; page exit releases it", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={(value) => { current = value; }} />);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  act(() => current!.bindings[1]!.onTurn(-5));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(1));
  const cutoffHz = fixture.controller.getState().filter.cutoffHz;
  // Group switches and page navigation never release the rotary gesture.
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  await userEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  selectPerformPage("Slots");
  selectPerformPage("Live");
  expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().filter.cutoffHz).toBe(cutoffHz);
  expect(fixture.controller.getState().filter.engaged).toBe(true);
  // Page exit is the one rotary release, frozen far-side under HOLD.
  await fixture.controller.leave();
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(2));
  expect(fixture.runtime.calls.liveControl.mock.calls[1]?.[0].intent).toEqual({
    kind: "filter_release", gestureGeneration: "generation-1",
  });
});

test("Delay touch and HOLD ride the typed generation route", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  const delay = screen.getByRole("slider", {name: "Delay"});
  fireEvent.pointerDown(delay, {pointerId: 4});
  fireEvent.change(delay, {target: {value: "630"}});
  fireEvent.pointerUp(delay, {pointerId: 4});
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(3));
  const intents = fixture.runtime.calls.liveControl.mock.calls
    .map(([request]) => request.intent);
  expect(intents[0]).toMatchObject({kind: "fx_parameter", phase: "engage",
    fx: "delay", value: 0});
  expect(intents[1]).toMatchObject({kind: "fx_parameter", phase: "move",
    fx: "delay", value: 630, gestureGeneration: "generation-1"});
  expect(intents[2]).toEqual({kind: "fx_release", fx: "delay",
    gestureGeneration: "generation-1"});
  await userEvent.click(screen.getByRole("button", {name: "HOLD"}));
  await waitFor(() =>
    expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(4));
  expect(fixture.runtime.calls.liveControl.mock.calls[3]?.[0].intent)
    .toEqual({kind: "hold_on"});
  // The legacy session-free gesture op stays silent on the typed route.
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
});

const TYPED_FX = ["delay", "reverb", "stutter", "gate", "reverse", "crush", "cutter"] as const;
test.each(TYPED_FX)("%s keeps its Core generation when move receipts carry no new binding", async fx => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const gesture = fixture.controller.engageFx(fx, 600);
  await waitFor(() => expect(fixture.controller.getState().fx[fx]).toBe(600));
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(2));
  fixture.controller.moveFx(gesture, fx, 630);
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(3));
  fixture.controller.moveFx(gesture, fx, 640);
  await waitFor(() => expect(calls.liveStatus).toHaveBeenCalledTimes(4));
  fixture.controller.releaseFx(gesture, fx);
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(4));
  expect(calls.liveControl.mock.calls.map(([request]) => request.intent)).toEqual([
    {kind: "fx_parameter", phase: "engage", fx, value: 600},
    {kind: "fx_parameter", phase: "move", fx, value: 630, gestureGeneration: "generation-1"},
    {kind: "fx_parameter", phase: "move", fx, value: 640, gestureGeneration: "generation-1"},
    {kind: "fx_release", fx, gestureGeneration: "generation-1"},
  ]);
});

test("headered recording adopts the Core begin mapping and never seeds a fake engage", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  const stateWithDelay = liveState();
  stateWithDelay.otherFx.delay = {engaged: true, frozen: false, value: 600};
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: stateWithDelay, applied: stateWithDelay,
  }));
  calls.begin.mockImplementation(headeredBegin([
    {fx: "delay", gestureGeneration: "gen-live-9",
      recordingGestureId: "rec-delay-1"},
  ]));
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  // The initial mirror is the Core readback, not a Host percentage default.
  expect(fixture.controller.getState().fx.delay).toBe(600);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() =>
    expect(fixture.controller.getState().recording.phase).toBe("recording"));
  expect(calls.begin.mock.calls[0]?.[0]).toMatchObject({
    controlEpoch: LIVE_EPOCH});
  // The D0 fence runs before the capture start, and the mapping-covered
  // gesture journals nothing at begin: no fake engage seeds the recording.
  expect(fixture.order.indexOf("begin")).toBeLessThan(
    fixture.order.indexOf("capture"));
  expect(calls.raw).not.toHaveBeenCalled();
  // A touch on the adopted gesture pairs move/release against the mapping.
  const delay = screen.getByRole("slider", {name: "Delay"});
  fireEvent.pointerDown(delay, {pointerId: 4});
  fireEvent.change(delay, {target: {value: "640"}});
  fireEvent.pointerUp(delay, {pointerId: 4});
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(3));
  const events = calls.raw.mock.calls.map(([request]) => request.event);
  expect(events[0]).toEqual({kind: "fx_move", fx: "delay", value: 600,
    gestureId: "rec-delay-1", gestureGeneration: "gen-live-9"});
  expect(events[1]).toEqual({kind: "fx_move", fx: "delay", value: 640,
    gestureId: "rec-delay-1", gestureGeneration: "gen-live-9"});
  expect(events[2]).toEqual({kind: "fx_release", fx: "delay",
    gestureId: "rec-delay-1", gestureGeneration: "gen-live-9"});
  // Recording applies gestures through the journal; the sessionless typed
  // producer stays silent meanwhile.
  expect(calls.liveControl).not.toHaveBeenCalled();
});

for (const starting of ["engaged", "frozen"] as const) {
  test.each(TYPED_FX)(`%s adopts the ${starting} Core recording start without synthetic events`, async fx => {
    const fixture = controllerFixture();
    const {calls} = fixture.runtime;
    const core = liveState({hold: starting === "frozen"});
    core.otherFx[fx] = {value: 700, engaged: starting === "engaged", frozen: starting === "frozen"};
    calls.liveStatus.mockImplementation(async () => liveStatusAvailable({accepted: core, applied: core}));
    const binding = {fx, gestureGeneration: "begin-generation", recordingGestureId: "begin-binding"};
    calls.begin.mockImplementation(headeredBegin(starting === "engaged" ? [binding] : []));
    calls.raw.mockImplementation(async ({eventId, event}) => ({eventId,
      gestureGeneration: event.kind === "fx_engage" ? "new-generation" : null,
      recordingGestureId: event.kind === "fx_engage" ? "new-binding" : null, replayed: false}));
    fixture.controller.connect();
    await fixture.controller.refreshRecovery();
    await fixture.controller.refreshLiveStatus();
    expect(fixture.controller.getState().fx[fx]).toBe(700);
    await fixture.controller.record();
    expect(calls.raw).not.toHaveBeenCalled();
    const gesture = fixture.controller.engageFx(fx, 640);
    await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
    // A move receipt carries no replacement binding in the actual Core.
    if (starting === "engaged") {
      expect(calls.raw.mock.calls[0]?.[0].event).toEqual({kind: "fx_move", fx, value: 640,
        gestureGeneration: "begin-generation", gestureId: "begin-binding"});
    } else {
      expect(calls.raw.mock.calls[0]?.[0].event).toEqual({kind: "fx_engage", fx, value: 640});
    }
    fixture.controller.releaseFx(gesture, fx);
    await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(2));
    expect(calls.raw.mock.calls[1]?.[0].event).toEqual({kind: "fx_release", fx,
      gestureGeneration: starting === "engaged" ? "begin-generation" : "new-generation",
      gestureId: starting === "engaged" ? "begin-binding" : "new-binding"});
    await fixture.controller.stop();
  });
}

test("headered begin keeps a mapped legacy Filter on the scalar event route", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  const scalar = liveState({filter: {mode: "legacy", value: 630,
    engaged: true, frozen: false}});
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: scalar, applied: scalar,
  }));
  calls.begin.mockImplementation(headeredBegin([{fx: "filter",
    gestureGeneration: "legacy-generation", recordingGestureId: "legacy-binding"}]));
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
  await fixture.controller.record();
  const gesture = fixture.controller.engageFx("filter", 640);
  fixture.controller.releaseFx(gesture, "filter");
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(2));
  expect(calls.raw.mock.calls.map(([request]) => request.event)).toEqual([
    {kind: "fx_move", fx: "filter", value: 640,
      gestureId: "legacy-binding", gestureGeneration: "legacy-generation"},
    {kind: "fx_release", fx: "filter", gestureId: "legacy-binding",
      gestureGeneration: "legacy-generation"},
  ]);
});

test("the three independent Filter parameters journal once each per recording", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  calls.raw.mockImplementation(async ({eventId}) => ({
    eventId, acceptedTick: 1, inputSequence: "1", nextRecordingSequence: "1",
    result: "published" as const, coalesced: false as const,
    gestureGeneration: "gen-rec-1", recordingGestureId: "rec-filter-1",
    replayed: false as const, projectRevision: null,
  }));
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() =>
    expect(fixture.controller.getState().recording.phase).toBe("recording"));
  act(() => fixture.controller.setFilterType("hp"));
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
  act(() => fixture.controller.turnFilterCutoff(-10));
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(2));
  act(() => fixture.controller.turnFilterResonance(5));
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(3));
  const events = calls.raw.mock.calls.map(([request]) => request.event);
  expect(events[0]).toEqual({kind: "filter_parameter", phase: "engage",
    parameter: "type", value: "hp"});
  expect(events[1]).toEqual({kind: "filter_parameter", phase: "move",
    parameter: "cutoff_hz", value: cutoffPositionToHz(900),
    gestureId: "rec-filter-1", gestureGeneration: "gen-rec-1"});
  expect(events[2]).toEqual({kind: "filter_parameter", phase: "move",
    parameter: "resonance_milli", value: 50,
    gestureId: "rec-filter-1", gestureGeneration: "gen-rec-1"});
});

test("the first Pad waits for the capture start ACK in a headered recording", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  const gate = deferred<void>();
  calls.capture.mockImplementation(async (sink: {onStopped(): void}) => {
    fixture.order.push("capture");
    await gate.promise;
    return {stop: vi.fn(async () => sink.onStopped())};
  });
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  // The Core fence proved (begin resolved) but the capture ACK is still out:
  // the first Pad is gated, not dropped into a silent journal.
  await waitFor(() => expect(calls.begin).toHaveBeenCalled());
  expect(fixture.controller.getState().recording.phase).toBe("starting");
  await fixture.controller.recordRawEvent({kind: "pad_press",
    gestureId: "pad-1", slot: 0, velocity: 100});
  expect(calls.raw).not.toHaveBeenCalled();
  gate.resolve();
  await waitFor(() =>
    expect(fixture.controller.getState().recording.phase).toBe("recording"));
  await fixture.controller.recordRawEvent({kind: "pad_press",
    gestureId: "pad-2", slot: 1, velocity: 100});
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
  expect(calls.raw.mock.calls[0]?.[0].event)
    .toMatchObject({kind: "pad_press", slot: 1});
});

test("headered capture start failure compensates the already committed begin", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  calls.capture.mockRejectedValueOnce(new Error("capture start refused"));
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  expect(calls.begin).toHaveBeenCalledTimes(1);
  expect(calls.capture).toHaveBeenCalledTimes(1);
  expect(calls.stop).toHaveBeenCalledWith({sessionId: ids.session,
    requestId: expect.any(String)});
  expect(fixture.store.discard).toHaveBeenCalledWith({
    expectedRevision: 8, performanceId: ids.performance,
  });
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.phase).toBe("idle");
  expect(calls.raw).not.toHaveBeenCalled();
});

test("an unavailable typed producer keeps the legacy Filter and says so", async () => {
  const fixture = controllerFixture();
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(false));
  // The legacy scalar fader stays; no Hz is guessed from a percentage.
  expect(screen.getByRole("slider", {name: "Filter"})).toBeTruthy();
  expect(screen.queryByText("20.0 kHz")).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "FILTER"}));
  expect(screen.getByRole("status", {name: "Filter status"}).textContent)
    .toContain("unavailable");
  expect(screen.getByRole("slider", {name: "Cutoff"})
    .hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("button", {name: "HP"}).hasAttribute("disabled"))
    .toBe(true);
  // Legacy gestures still take the legacy route.
  const filter = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "630"}});
  fireEvent.pointerUp(filter, {pointerId: 3});
  await waitFor(() =>
    expect(fixture.runtime.calls.fx).toHaveBeenCalledTimes(3));
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
});

test("a far-side rejection surfaces and the next control re-engages honestly", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  calls.liveControl.mockRejectedValueOnce(Object.assign(
    new Error("stale control epoch"), {code: "PROJECT_BUSY"}));
  act(() => fixture.controller.turnFilterCutoff(-1));
  await waitFor(() =>
    expect(fixture.controller.getState().error).not.toBeNull());
  expect(calls.liveControl).toHaveBeenCalledTimes(1);
  // The failed engage issued no generation, so the next turn engages afresh
  // instead of moving on a generation the Core never issued.
  act(() => fixture.controller.turnFilterCutoff(-1));
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(2));
  expect(calls.liveControl.mock.calls[1]?.[0].intent)
    .toMatchObject({phase: "engage", parameter: "cutoff_hz"});
  await waitFor(() =>
    expect(fixture.controller.getState().filter.provenance).toBe("core"));
});

test("HOLD freeze is shown only from the Core readback after release", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  await userEvent.click(screen.getByRole("button", {name: "HOLD"}));
  const cutoff = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(cutoff, {pointerId: 3});
  fireEvent.change(cutoff, {target: {value: "700"}});
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(3));
  const frozen = liveState({hold: true, filter: {
    mode: "independent" as const, engaged: false, frozen: true,
    type: "lp" as const, cutoffHz: cutoffPositionToHz(700), resonanceMilli: 0,
  }});
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: frozen, applied: frozen,
  }));
  fireEvent.pointerUp(cutoff, {pointerId: 3});
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(4));
  expect(calls.liveControl.mock.calls[3]?.[0].intent).toEqual({
    kind: "filter_release", gestureGeneration: "generation-2",
  });
  await waitFor(() =>
    expect(fixture.controller.getState().filter.frozen).toBe(true));
  expect(fixture.controller.getState().filter).toMatchObject({
    engaged: false, provenance: "core", cutoffHz: cutoffPositionToHz(700),
  });
  expect(fixture.controller.getState().hold).toBe(true);
});

test("a recording-time Filter release reads frozen back from Core", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  const engaged = liveState({filter: {
    mode: "independent" as const, engaged: true, frozen: false,
    type: "lp" as const, cutoffHz: 2000, resonanceMilli: 100,
  }});
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: engaged, applied: engaged,
  }));
  calls.begin.mockImplementation(headeredBegin([
    {fx: "filter", gestureGeneration: "gen-live-1",
      recordingGestureId: "rec-filter-1"},
  ]));
  renderSurface(fixture);
  await waitFor(() =>
    expect(fixture.controller.getState().filter.engaged).toBe(true));
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() =>
    expect(fixture.controller.getState().recording.phase).toBe("recording"));
  // The release pairs against the begin mapping; the frozen flag arrives only
  // with the release-settled Core readback.
  const frozen = liveState({filter: {
    mode: "independent" as const, engaged: false, frozen: true,
    type: "lp" as const, cutoffHz: 2000, resonanceMilli: 100,
  }});
  calls.liveStatus.mockImplementation(async () => liveStatusAvailable({
    accepted: frozen, applied: frozen,
  }));
  const token = fixture.controller.touchFilterEngage("cutoff");
  fixture.controller.touchFilterRelease(token, "cutoff");
  await waitFor(() =>
    expect(fixture.controller.getState().filter.frozen).toBe(true));
  expect(fixture.controller.getState().filter).toMatchObject({
    engaged: false, provenance: "core", cutoffHz: 2000,
  });
  expect(calls.raw.mock.calls.map(([request]) => request.event))
    .toContainEqual({kind: "filter_release", gestureId: "rec-filter-1",
      gestureGeneration: "gen-live-1"});
});

test("a legacy Filter gesture opened before the first status answer keeps its route until release", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  const statusGate = deferred<ReturnType<typeof liveStatusAvailable>>();
  calls.liveStatus.mockImplementation(() => statusGate.promise);
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onEncodersReady={(value) => { current = value; }} />);
  // The answer is still in flight: the fader and ENC1 are the legacy scalar
  // Filter and gestures take the legacy route.
  const filter = screen.getByRole("slider", {name: "Filter"});
  expect((filter as HTMLInputElement).value).toBe("500");
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Filter", "Delay", "Reverb"]);
  fireEvent.pointerDown(filter, {pointerId: 3});
  fireEvent.change(filter, {target: {value: "630"}});
  await waitFor(() => expect(calls.fx).toHaveBeenCalledTimes(2));
  // The typed producer answers while the legacy gesture is open: neither the
  // surface nor the gesture flips route mid-gesture.
  act(() => { statusGate.resolve(liveStatusAvailable()); });
  await waitFor(() =>
    expect(fixture.controller.getState().liveControl.available).toBe(true));
  expect(fixture.controller.getState().legacyFilterGesture).toBe(true);
  expect((screen.getByRole("slider", {name: "Filter"}) as HTMLInputElement)
    .value).toBe("630");
  expect(screen.getByText("63%")).toBeTruthy();
  expect(screen.queryByText("20.0 kHz")).toBeNull();
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Filter", "Delay", "Reverb"]);
  // An alternate FILTER-group binding cannot bypass the pinned legacy
  // lifetime while the same physical gesture is still open.
  act(() => {
    fixture.controller.turnFilterType(1);
    fixture.controller.turnFilterCutoff(-1);
    fixture.controller.turnFilterResonance(1);
  });
  expect(calls.liveControl).not.toHaveBeenCalled();
  fireEvent.change(filter, {target: {value: "640"}});
  await waitFor(() => expect(calls.fx).toHaveBeenCalledTimes(3));
  expect(calls.liveControl).not.toHaveBeenCalled();
  // Release closes the gesture on its original route; only then does the
  // surface adopt the typed Cutoff readback.
  fireEvent.pointerUp(filter, {pointerId: 3});
  await waitFor(() => expect(calls.fx).toHaveBeenCalledTimes(4));
  expect(calls.fx.mock.calls.map(([event]) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_move", "fx_release"]);
  expect(calls.liveControl).not.toHaveBeenCalled();
  await waitFor(() =>
    expect(fixture.controller.getState().legacyFilterGesture).toBe(false));
  expect((screen.getByRole("slider", {name: "Filter"}) as HTMLInputElement)
    .value).toBe("1000");
  expect(screen.getByText("20.0 kHz")).toBeTruthy();
  expect(Object.values(current!.bindings).map((binding) => binding.label))
    .toEqual(["Cutoff", "Delay", "Reverb"]);
});

// C2: the masks below are producer readbacks, never a Host-authored Project.
test("current Pad controls expose independent multi-Solo and Mute priority across all 64 slots", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  const view = render(<PerformSurface controller={fixture.controller} project={project}
    bank={0} currentPad={0} />);
  await waitFor(() => expect(screen.getByRole("button", {name: "Solo A01"})).toHaveProperty("disabled", false));
  fireEvent.click(screen.getByRole("button", {name: "Solo A01"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Solo A01"}).getAttribute("aria-pressed")).toBe("true"));
  view.rerender(<PerformSurface controller={fixture.controller} project={project}
    bank={3} currentPad={63} />);
  expect(screen.getByRole("status", {name: "Live Pad status"}).textContent).toContain("Silenced · other Pads soloed");
  fireEvent.click(screen.getByRole("button", {name: "Solo D16"}));
  await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([0, 63]));
  fireEvent.click(screen.getByRole("button", {name: "Mute D16"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Mute D16"}).getAttribute("aria-pressed")).toBe("true"));
  expect(screen.getByRole("button", {name: "Solo D16"}).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("status", {name: "Live Pad status"}).textContent).toContain("Silenced · Mute");
  expect(selectLivePadGate(fixture.controller.getState().padGates, 0)).toEqual({muted: false, solo: true, silenced: false});
  view.rerender(<PerformSurface controller={fixture.controller} project={project}
    bank={0} currentPad={0} />);
  expect(screen.getByRole("button", {name: "Solo A01"}).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByRole("button", {name: "Mute A01"}).getAttribute("aria-pressed")).toBe("false");
  expect(fixture.runtime.session.savePerformance).not.toHaveBeenCalled();
});

test("Pad gate admission stays pending until the applied mask is read back", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const stale = await calls.liveStatus();
  const delayed = deferred<unknown>();
  calls.liveStatus.mockImplementationOnce(() => delayed.promise);
  fixture.controller.togglePadGate("mute", 63);
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(1));
  expect(fixture.controller.getState().padGates).toMatchObject({mutedSlots: [], provenance: "pending"});
  fixture.controller.togglePadGate("solo", 0);
  expect(calls.liveControl).toHaveBeenCalledTimes(1);
  delayed.resolve({...stale as object, acceptedControlSequence: "1"});
  await waitFor(() => expect(fixture.controller.getState().padGates).toMatchObject({mutedSlots: [63], provenance: "core"}));
});

test("unavailable Pad gates preserve unknown state and send no fabricated neutral command", async () => {
  const fixture = controllerFixture();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0} currentPad={0} />);
  expect(screen.getByRole("button", {name: "Mute A01"})).toHaveProperty("disabled", true);
  expect(screen.getByRole("status", {name: "Live Pad status"}).textContent).toContain("Unavailable");
  fixture.controller.togglePadGate("mute", 0);
  await fixture.controller.leave();
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
});

test("leave waits for the far-side empty masks and HOLD cannot preserve Pad gates", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  fixture.controller.togglePadGate("solo", 63);
  await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
  fixture.controller.toggleHold();
  await waitFor(() => expect(fixture.controller.getState().hold).toBe(true));
  await fixture.controller.refreshLiveStatus();
  const old = await calls.liveStatus();
  const wait = deferred<unknown>();
  calls.liveStatus.mockImplementationOnce(() => wait.promise);
  let left = false;
  const leaving = fixture.controller.leave().then(() => { left = true; });
  await waitFor(() => expect(calls.liveControl.mock.calls.at(-1)?.[0].intent.kind).toBe("clear_pad_gates"));
  fixture.controller.togglePadGate("mute", 0);
  expect(left).toBe(false);
  wait.resolve({...old as object, acceptedControlSequence: "3"});
  await leaving;
  expect(fixture.controller.getState().padGates).toMatchObject({mutedSlots: [], soloSlots: [], provenance: "core"});
  expect(fixture.controller.getState().hold).toBe(true);
  expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind)).toEqual(["pad_solo", "hold_on", "clear_pad_gates"]);
});

test("a Pad control queued for an old epoch cannot mutate its replacement", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  const delayed = deferred<Awaited<ReturnType<typeof calls.liveControl>>>();
  calls.liveControl.mockImplementationOnce(() => delayed.promise);
  fixture.controller.turnFx("delay", 1);
  await waitFor(() => expect(calls.liveControl).toHaveBeenCalledTimes(1));
  fixture.controller.togglePadGate("mute", 63);
  calls.liveStatus.mockResolvedValue(liveStatusAvailable({controlEpoch: "replacement"}));
  await fixture.controller.refreshLiveStatus();
  delayed.resolve({commandId: "old", controlEpoch: LIVE_EPOCH, controlSequence: "1",
    gestureGeneration: "old", accepted: true, applied: true, replayed: false, projectRevision: null});
  await fixture.controller.refreshLiveStatus();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(calls.liveControl).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().padGates.mutedSlots).toEqual([]);
});

test("recording freezes preexisting Pad masks and journals later changes and leave cleanup", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  fixture.controller.togglePadGate("solo", 63);
  await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
  let initial: unknown;
  calls.begin.mockImplementation(async (request) => {
    initial = (await calls.liveStatus() as ReturnType<typeof liveStatusAvailable>).applied;
    return headeredBegin()(request);
  });
  await fixture.controller.record();
  expect(initial).toMatchObject({soloSlots: [63], mutedSlots: []});
  expect(calls.raw).not.toHaveBeenCalled();
  fixture.controller.togglePadGate("mute", 63);
  await waitFor(() => expect(fixture.controller.getState().padGates.mutedSlots).toEqual([63]));
  await fixture.controller.leave();
  expect(calls.raw.mock.calls.map(([request]) => request.event)).toEqual([
    {kind: "pad_mute", slot: 63, enabled: true}, {kind: "clear_pad_gates"},
  ]);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
  expect(fixture.controller.getState().padGates).toMatchObject({mutedSlots: [], soloSlots: []});
  expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind)).toEqual(["pad_solo"]);
});

for (const exit of ["leave", "close"] as const) {
  test(`Pad gate ${exit} rejects an owner epoch replacement during reset acknowledgement`, async () => {
    const fixture = controllerFixture();
    const {calls} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    fixture.controller.togglePadGate("solo", 63);
    await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
    const replacementEpoch = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const replacement = liveState({mutedSlots: [9]});
    calls.liveStatus.mockResolvedValue(liveStatusAvailable({
      controlEpoch: replacementEpoch, accepted: replacement, applied: replacement,
    }));
    await expect(fixture.controller[exit]()).rejects.toThrow(
      "Performance Pad gate owner changed before reset acknowledgement");
    expect(calls.liveControl.mock.calls.filter(([request]) =>
      request.intent.kind === "clear_pad_gates")).toHaveLength(1);
    expect(calls.liveControl.mock.calls.every(([request]) =>
      request.controlEpoch === LIVE_EPOCH)).toBe(true);
    expect(fixture.controller.getState().padGates).not.toMatchObject({
      mutedSlots: [], soloSlots: [], provenance: "core",
    });
  });
}

test("a refused gate reset blocks leave instead of declaring empty masks", async () => {
  const fixture = controllerFixture({maximumStatusQueries: 2, waitForStatusQuery: async () => {}});
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  fixture.controller.togglePadGate("mute", 0);
  await waitFor(() => expect(fixture.controller.getState().padGates.mutedSlots).toEqual([0]));
  calls.liveControl.mockRejectedValueOnce(new Error("reset refused"));
  await expect(fixture.controller.leave()).rejects.toThrow("reset refused");
  expect(fixture.controller.getState().padGates.mutedSlots).toEqual([0]);
});

for (const exit of ["leave", "close"] as const) {
  test(`${exit} retires an active Replay publisher before acknowledging empty Pad masks`, async () => {
    const fixture = controllerFixture({maximumStatusQueries: 2,
      waitForStatusQuery: async () => {}});
    const {calls, session} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    fixture.controller.togglePadGate("solo", 63);
    await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
    let replaying = true;
    const read = calls.liveStatus.getMockImplementation()!;
    calls.liveStatus.mockImplementation(async () => {
      const status = await read() as ReturnType<typeof liveStatusAvailable>;
      // The recorded mask remains published while Replay owns the sink.
      // Clearing the live mask alone cannot establish an empty readback.
      return replaying ? {...status, applied: {...status.applied, soloSlots: [63]}} : status;
    });
    (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
      .mockResolvedValue({replayId: "replay-1", state: "playing", resolvedRevision: 7,
        eventCursor: 0, eventCount: 4, projectRevision: null});
    (session.stopPerformanceReplay as ReturnType<typeof vi.fn>)
      .mockImplementation(async ({requestId}) => {
        replaying = false;
        return {replayId: "replay-1", requestId, state: "stopped", resolvedRevision: 7,
          eventCursor: 0, eventCount: 4, replayed: false, projectRevision: null};
      });
    await fixture.controller.beginReplay(ids.performance);
    await fixture.controller[exit]();
    expect(session.stopPerformanceReplay).toHaveBeenCalledTimes(1);
    expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind))
      .toEqual(["pad_solo", "clear_pad_gates"]);
    const status = await calls.liveStatus() as ReturnType<typeof liveStatusAvailable>;
    expect(status.applied).toMatchObject({mutedSlots: [], soloSlots: []});
    if (exit === "leave") {
      expect(fixture.controller.getState().padGates)
        .toMatchObject({mutedSlots: [], soloSlots: [], provenance: "core"});
    }
    expect(calls.raw).not.toHaveBeenCalled();
  });
}

for (const exit of ["leave", "close"] as const) {
  test(`P2 ${exit} awaits an admitted begin and its terminal publisher before mask clear`, async () => {
    const fixture = controllerFixture();
    const {calls, session} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    fixture.controller.togglePadGate("solo", 63);
    await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
    const beginReply = deferred<unknown>();
    const neutralFence = deferred<void>();
    const clearReply = deferred<void>();
    let publishing = false;
    const begin = session.beginPerformanceReplay as ReturnType<typeof vi.fn>;
    const stop = session.stopPerformanceReplay as ReturnType<typeof vi.fn>;
    begin.mockImplementation(() => beginReply.promise.then((reply) => {
      publishing = true;
      return reply;
    }));
    stop.mockImplementation(async ({replayId, requestId}) => {
      await neutralFence.promise;
      publishing = false;
      return {replayId, requestId, state: "stopped", resolvedRevision: 7,
        eventCursor: 0, eventCount: 4, replayed: false, projectRevision: null};
    });
    const apply = calls.liveControl.getMockImplementation()!;
    calls.liveControl.mockImplementation(async (request) => {
      if (request.intent.kind === "clear_pad_gates") await clearReply.promise;
      return apply(request);
    });
    const entering = fixture.controller.beginReplay(ids.performance);
    let exited = false;
    let exitError: unknown;
    const leaving = fixture.controller[exit]().then(() => { exited = true; },
      (error) => { exitError = error; });
    try {
      // On the frozen candidate this puts begin's reply inside the exit's
      // post-check clear wait. The repair instead waits for admitted begin.
      await new Promise((resolve) => setTimeout(resolve, 0));
      beginReply.resolve({replayId: begin.mock.calls[0]![0].replayId,
        state: "playing", resolvedRevision: 7, eventCursor: 0, eventCount: 4,
        projectRevision: null});
      await entering;
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(stop, "admitted begin's publisher must reach Stop before clear")
        .toHaveBeenCalledTimes(1);
      expect(exited).toBe(false);
      expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind))
        .toEqual(["pad_solo"]);
    } finally {
      neutralFence.resolve();
      clearReply.resolve();
      await leaving;
    }
    expect(exitError).toBeUndefined();
    expect(exited).toBe(true);
    expect(publishing, "exit cannot complete with a live Replay publisher").toBe(false);
    const status = await calls.liveStatus() as ReturnType<typeof liveStatusAvailable>;
    expect(status.applied).toMatchObject({mutedSlots: [], soloSlots: []});
  });

  test(`P2 ${exit} refuses a new begin while exit acknowledgement is pending`, async () => {
    const fixture = controllerFixture();
    const {calls, session} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    fixture.controller.togglePadGate("solo", 63);
    await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
    const clearReply = deferred<void>();
    const apply = calls.liveControl.getMockImplementation()!;
    calls.liveControl.mockImplementation(async (request) => {
      if (request.intent.kind === "clear_pad_gates") await clearReply.promise;
      return apply(request);
    });
    const begin = session.beginPerformanceReplay as ReturnType<typeof vi.fn>;
    begin.mockResolvedValue({replayId: "late-begin", state: "stopped",
      resolvedRevision: 7, eventCursor: 0, eventCount: 0, projectRevision: null});
    const leaving = fixture.controller[exit]();
    try {
      await waitFor(() => expect(calls.liveControl.mock.calls.at(-1)?.[0].intent.kind)
        .toBe("clear_pad_gates"));
      await fixture.controller.beginReplay(ids.performance);
      expect(begin, "exit admission must close Session begin admission").not.toHaveBeenCalled();
    } finally {
      clearReply.resolve();
      await leaving;
    }
  });

  test(`P2 ${exit} preserves an unknown admitted-begin failure instead of completing exit`, async () => {
    const reportFailure = vi.fn();
    const fixture = controllerFixture({reportFailure});
    const {calls, session} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    fixture.controller.togglePadGate("solo", 63);
    await waitFor(() => expect(fixture.controller.getState().padGates.soloSlots).toEqual([63]));
    const beginReply = deferred<unknown>();
    (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
      .mockImplementation(() => beginReply.promise);
    const entering = fixture.controller.beginReplay(ids.performance);
    const leaving = fixture.controller[exit]().then(
      () => ({state: "completed" as const}),
      (error: unknown) => ({state: "failed" as const, error}));
    const error = Object.assign(new Error("Replay begin receipt unavailable"), {code: "HOST_TIMEOUT"});
    beginReply.reject(error);
    await entering;
    const result = await leaving;
    expect(result, "an unknown begin cannot establish publisher quiescence")
      .toEqual({state: "failed", error});
    expect(reportFailure).toHaveBeenCalledWith("Perform", error);
    expect(fixture.controller.getState().error).not.toBeNull();
    expect(calls.liveControl.mock.calls.map(([request]) => request.intent.kind))
      .toEqual(["pad_solo"]);
  });
}

for (const take of ["same", "other"] as const) {
  test(`P2 already-playing ${take} take admits no redundant begin and preserves Stop, leave, new begin`, async () => {
    const fixture = controllerFixture();
    const {calls, session} = fixture.runtime;
    enableTypedCore(calls);
    await fixture.controller.refreshLiveStatus();
    let activeReplayId: string | null = null;
    let producerBegins = 0;
    const begin = session.beginPerformanceReplay as ReturnType<typeof vi.fn>;
    const stop = session.stopPerformanceReplay as ReturnType<typeof vi.fn>;
    begin.mockImplementation(async ({replayId}) => {
      if (activeReplayId !== null) {
        // Facade refuses before a second producer begins. SDK keeps these
        // validated fields but replaces the original human message.
        throw Object.assign(new Error("Host request was rejected"), {
          name: "HostProtocolError", code: "INVALID_ARGUMENT",
          details: Object.freeze({active_replay_id: activeReplayId}),
        });
      }
      producerBegins += 1;
      activeReplayId = replayId;
      return {replayId, state: "playing", resolvedRevision: 7,
        eventCursor: 0, eventCount: 4, projectRevision: null};
    });
    stop.mockImplementation(async ({replayId, requestId}) => {
      expect(replayId, "Stop must retire the original owner").toBe(activeReplayId);
      activeReplayId = null;
      return {replayId, requestId, state: "stopped", resolvedRevision: 7,
        eventCursor: 0, eventCount: 4, replayed: false, projectRevision: null};
    });
    await fixture.controller.beginReplay(ids.performance);
    const originalReplayId = fixture.controller.getState().replay!.replayId;
    const nextTake = take === "same" ? ids.performance : "88888888-8888-4888-8888-888888888888";
    await fixture.controller.beginReplay(nextTake);
    expect(begin, "public playing truth must prevent a redundant Session begin")
      .toHaveBeenCalledTimes(1);
    expect(producerBegins).toBe(1);
    expect(fixture.controller.getState().replay)
      .toMatchObject({replayId: originalReplayId, state: "playing"});
    await fixture.controller.stopReplay();
    expect(stop).toHaveBeenCalledTimes(1);
    expect(activeReplayId).toBeNull();
    await fixture.controller.leave();
    const status = await calls.liveStatus() as ReturnType<typeof liveStatusAvailable>;
    expect(status.applied).toMatchObject({mutedSlots: [], soloSlots: []});
    await fixture.controller.beginReplay(nextTake);
    expect(begin).toHaveBeenCalledTimes(2);
    expect(begin.mock.calls[1]![0].performanceId).toBe(nextTake);
    expect(producerBegins).toBe(2);
    expect(fixture.controller.getState().replay)
      .toMatchObject({replayId: activeReplayId, state: "playing"});
    expect(fixture.controller.getState().error).toBeNull();
  });
}

test("P2 a post-publication INVALID_ARGUMENT remains ambiguous and blocks exit", async () => {
  const reportFailure = vi.fn();
  const fixture = controllerFixture({reportFailure});
  const {calls, session} = fixture.runtime;
  enableTypedCore(calls);
  await fixture.controller.refreshLiveStatus();
  let publishing = false;
  const error = Object.assign(new Error("Host request was rejected"), {
    name: "HostProtocolError", code: "INVALID_ARGUMENT", details: Object.freeze({}),
  });
  (session.beginPerformanceReplay as ReturnType<typeof vi.fn>)
    .mockImplementation(async () => {
      publishing = true; // producer published, but header/reset outcome is unknown
      throw error;
    });
  await fixture.controller.beginReplay(ids.performance);
  await expect(fixture.controller.leave()).rejects.toBe(error);
  expect(publishing).toBe(true);
  expect(reportFailure).toHaveBeenCalledWith("Perform", error);
  expect(calls.liveControl).not.toHaveBeenCalled();
  expect(fixture.controller.getState().error).not.toBeNull();
  expect(fixture.controller.getState().replay).toBeNull();
});
