import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {createRuntimeSession} from "@lmdj/web-runtime-platform/runtime_session.mjs";
import {useEffect} from "react";
import {RuntimeProvider, useRuntime} from "../src/runtime/runtime_context";
import type {RuntimeDiagnostics, RuntimeHostState} from "../src/runtime/runtime_types";
import {PerformanceRecordingStore} from "../src/record/performance_recording_store";
import {openWavStreamWriter} from "../src/record/wav_stream_writer";

import type {ContextualEncoders, ContextualNavigation} from "../src/components/physical_controls";
import type {PatternTransportStatus, PerformanceMasterCapture, PerformanceEventResult} from
  "@lmdj/web-runtime-platform/runtime_types";
import {FxSliderBank} from "../src/components/fx_slider_bank";
import {PerformSurface} from "../src/components/perform_surface";
import {RecordingAudioReadout} from "../src/components/recording_audio_readout";
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
  type PerformanceSummary,
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
    // Flexible doubles retain headered receipts; prepare forwards the same physical key.
    prepare: vi.fn((request: {eventId: string; event: Record<string, unknown>;
      sessionId: string}, physicalKey?: object): {
        submit(): Promise<PerformanceEventResult>; cancelBeforeSubmit(): boolean;
      } => ({
      submit: () => (physicalKey === undefined ? calls.raw(request) : calls.raw(request, physicalKey)) as Promise<PerformanceEventResult>,
      cancelBeforeSubmit: () => true,
    })),
    raw: vi.fn(async ({eventId}: {eventId: string; event: Record<string, unknown>;
      sessionId: string}, _physicalKey?: object): Promise<unknown> => ({eventId,
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
    stop: vi.fn(async (_request: {sessionId: string; requestId: string}) => ({requestId: "stop", sessionId: ids.session,
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
    preparePerformancePadEvent: calls.prepare,
    applyFxGesture: calls.fx,
    applyPerformanceLiveControl: calls.liveControl,
    queryPerformanceLiveStatus: calls.liveStatus,
    requestPerformancePatternLaunch: calls.launch,
    flushPerformanceRecording: calls.flush,
    stopPerformanceRecording: calls.stop,
    queryPerformanceRecordingStatus: vi.fn(async () => authority({state: "idle",
      sessionId: null, performanceId: null, journalRevision: 0, nextFlushSequence: 0})),
    listPerformances: vi.fn(async () => []),
    inspectPerformance: vi.fn(),
    queryPerformanceRecordingMetadata: vi.fn(async (_request: unknown,
      _options?: {signal?: AbortSignal}): Promise<unknown> => {
      throw Object.assign(new Error("Fixture has no saved WAV bytes"), {code: "IO_ERROR"});
    }),
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
    "queryPerformanceRecordingStatus",
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
  createId?: () => string;
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
    createId: options.createId ?? (() => {
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

test("renders the first-screen FX chain and one HOLD before the four-slot launch strip", () => {
  renderSurface();
  const surface = screen.getByRole("main", {name: "Perform"});
  const pattern = within(surface).getByRole("region", {name: "Pattern Launch"});
  const fx = within(surface).getByRole("region", {name: "Performance FX"});
  const hold = within(surface).getByRole("button", {name: "HOLD"});
  // The console's Pad matrix is the one Pad surface; Perform mounts none of
  // its own, so a second identical grid never competes for the same names.
  expect(within(surface).queryByRole("region", {name: "Perform instrument"})).toBeNull();
  expect(fx.compareDocumentPosition(pattern) & Node.DOCUMENT_POSITION_FOLLOWING).not.toBe(0);
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
// settling transport keeps them closed, and so does a missing projection.
// Open global Pattern recording delegates through that same path.
test("Launch during global Pattern recording selects through transport and stays closed while settling", async () => {
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
  const onSelectPattern = vi.fn();
  const view = render(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={status({playing: true, recording: true})} onSelectPattern={onSelectPattern} />);
  const launch = screen.getByRole("button", {name: /^Launch Pattern 1$/});
  expect(launch.hasAttribute("disabled")).toBe(false);
  await userEvent.click(launch);
  expect(onSelectPattern).toHaveBeenCalledExactlyOnceWith(ids.pattern1);
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={status({playing: true, recording: true})} onSelectPattern={onSelectPattern}
      patternSelectionLocked />);
  expect(screen.getByRole("button", {name: /^Launch Pattern 1$/})
    .hasAttribute("disabled")).toBe(true);
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      transport={status({phase: "preparing"})} onSelectPattern={onSelectPattern} />);
  expect(screen.getByRole("button", {name: /^Launch Pattern 1$/})
    .hasAttribute("disabled")).toBe(true);
  view.rerender(
    <PerformSurface controller={fixture.controller} project={project} bank={0}
      onSelectPattern={onSelectPattern} />);
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

test("keeps the other five confirmed FX behind MORE", async () => {
  renderSurface();
  const fx = screen.getByRole("region", {name: "Performance FX"});
  const more = within(fx).getByRole("button", {name: "MORE"});
  expect(more.getAttribute("aria-expanded")).toBe("false");
  expect(within(fx).queryByRole("slider", {name: "Stutter"})).toBeNull();

  await userEvent.click(more);
  expect(more.getAttribute("aria-expanded")).toBe("true");
  expect(within(fx).getAllByRole("slider").map((slider) => slider.getAttribute("aria-label")))
    .toEqual(["Stutter", "Gate", "Reverse", "Crush", "Cutter"]);

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

test("unknown capture start failure retains the temporary WAV without beginning Core", async () => {
  const fixture = controllerFixture();
  const original = new Error("tap unavailable");
  fixture.runtime.calls.capture.mockImplementationOnce(async () => {
    fixture.order.push("capture");
    throw original;
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.begin).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  expect(fixture.order).toEqual(["writer", "queue", "capture"]);
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
  await expect(fixture.controller.close()).rejects.toBe(original);
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

test("unknown begin failure stops capture, drains its tail, and retains the temporary WAV", async () => {
  const fixture = controllerFixture();
  const original = new Error("begin rejected");
  fixture.runtime.calls.begin.mockImplementationOnce(async () => {
    fixture.order.push("begin");
    throw original;
  });
  renderSurface(fixture);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await waitFor(() => expect(fixture.controller.getState().recording.phase).toBe("stopped"));
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.order).toEqual([
    "writer", "queue", "capture", "begin", "capture-stop", "tail-drained",
  ]);
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.sessionId).toBe(ids.session);
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
  expect(fixture.controller.getState().recording.expectedRevision).toBeNull();
  expect(fixture.controller.getState().wavStatus).toContain("temporary retained");
  await expect(fixture.controller.close()).rejects.toBe(original);
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

test("releases an open FX gesture when MORE collapses it away", async () => {
  const {fixture} = renderSurface();
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  const more = screen.getByRole("button", {name: "MORE"});
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
  // Both original Press and its synthetic matching Release reserve SDK
  // ownership now; the Host submits Release after the held receipt. The
  // later external Press remains refused by the Host stopping phase.
  expect(fixture.runtime.calls.prepare.mock.calls.map(([request]) => request.event))
    .toEqual([{kind: "pad_press", gestureId: "open", slot: 0, velocity: 100},
      {kind: "pad_release", gestureId: "open", slot: 0}]);
  firstEvent.resolve({eventId: "event", acceptedTick: 1, inputSequence: 1,
    coalesced: false, replayed: false, projectRevision: null});
  await Promise.all([first, stopping]);
  expect(fixture.runtime.calls.raw.mock.calls.map(([request]) => request.event))
    .toEqual([{kind: "pad_press", gestureId: "open", slot: 0, velocity: 100},
      {kind: "pad_release", gestureId: "open", slot: 0}]);
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

for (const [kind, invalid] of [["empty", ""], ["ASCII65", "x".repeat(65)],
  ["Unicode65", "🎵".repeat(65)]] as const) {
  test(`Performance name preflight refuses fresh ${kind} without touching its stopped WAV`, async () => {
    const f = controllerFixture();
    await f.controller.refreshRecovery();await f.controller.record();await f.controller.stop();
    const stopped = f.controller.getState().recording;
    expect(stopped.wav).not.toBeNull();
    await f.controller.save(invalid);
    expect(f.runtime.session.savePerformance, "an invalid fresh name must not enter the SDK")
      .not.toHaveBeenCalled();
    expect(f.runtime.session.inspectPerformance).not.toHaveBeenCalled();
    expect(f.store.bind).not.toHaveBeenCalled();
    expect(f.cleanupTemporary).not.toHaveBeenCalled();
    expect(f.controller.getState().recording).toEqual(stopped);
    expect(f.controller.getState().error).toBe("Use 1–64 characters for the Performance name.");
    await f.controller.save("🎵".repeat(64));
    expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
    expect(vi.mocked(f.runtime.session.savePerformance).mock.calls[0]![0].name).toBe("🎵".repeat(64));
    expect(f.store.bind).toHaveBeenCalledOnce();
    expect(f.controller.getState().bindingStatus).toBe("bound");
  });
}

test("Performance name preflight leaves an invalid fresh recording explicitly discardable", async () => {
  const f = controllerFixture();
  await f.controller.refreshRecovery();await f.controller.record();await f.controller.stop();
  await f.controller.save("x".repeat(65));
  await f.controller.discard();
  expect(f.store.discard).toHaveBeenCalledOnce();
  expect(f.store.discard).toHaveBeenCalledWith(expect.objectContaining({performanceId: ids.performance}));
  expect(f.runtime.session.savePerformance).not.toHaveBeenCalled();
  expect(f.runtime.session.inspectPerformance).not.toHaveBeenCalled();
  expect(f.controller.getState().recording.phase).toBe("idle");
});

test("Performance name preflight shows accessible feedback and admits an intact Unicode64 correction", async () => {
  const f = controllerFixture();renderSurface(f);
  await act(() => f.controller.refreshRecovery());
  await act(() => f.controller.record());await act(() => f.controller.stop());
  selectPerformPage("Takes");
  const input = screen.getByRole("textbox", {name: "Performance name"});
  const save = screen.getByRole("button", {name: "Save Performance"});
  for (const value of ["x".repeat(65), "🎵".repeat(65), "", "   "]) {
    fireEvent.change(input, {target: {value}});
    expect((input as HTMLInputElement).value).toBe(value);
    expect(save.hasAttribute("disabled"), "the fresh invalid name must not be submittable").toBe(true);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    const description = document.getElementById(input.getAttribute("aria-describedby")!);
    expect(description?.textContent).toBe("Use 1–64 characters for the Performance name.");
    expect(screen.getByRole("alert")).toBe(description);
    for (const action of ["Discard Performance", "Export Performance WAV"]) {
      expect(screen.getByRole("button", {name: action}).hasAttribute("disabled")).toBe(false);
    }
  }
  expect(f.runtime.session.savePerformance).not.toHaveBeenCalled();
  expect(f.runtime.session.inspectPerformance).not.toHaveBeenCalled();
  expect(f.store.bind).not.toHaveBeenCalled();
  const legal = "🎵".repeat(64);
  fireEvent.change(input, {target: {value: ` ${legal} `}});
  expect(save.hasAttribute("disabled")).toBe(false);
  expect(input.hasAttribute("aria-invalid")).toBe(false);
  expect(screen.queryByRole("alert")).toBeNull();
  await userEvent.click(save);
  await waitFor(() => expect(f.controller.getState().bindingStatus).toBe("bound"));
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(vi.mocked(f.runtime.session.savePerformance).mock.calls[0]![0].name).toBe(legal);
});

test("Performance name preflight never blocks the original UNKNOWN inspection with an invalid replacement", async () => {
  const f = controllerFixture();
  await f.controller.refreshRecovery();await f.controller.record();await f.controller.stop();
  vi.mocked(f.runtime.session.savePerformance).mockRejectedValueOnce(Object.assign(
    new Error("published Save reply invalid"), {code: "INVALID_ARGUMENT"}));
  vi.mocked(f.runtime.session.inspectPerformance).mockRejectedValueOnce(new Error("inspection unavailable"));
  await f.controller.save("Owned take");
  expect(f.controller.getState().error).toContain("could not confirm the save");
  expect(f.controller.getState().recording.phase).toBe("stopped");
  expect(f.store.bind).not.toHaveBeenCalled();
  vi.mocked(f.runtime.session.inspectPerformance).mockResolvedValueOnce({id: ids.performance,
    name: "Owned take", createdBpm: 120, recordingArtifact: null, events: [], projectRevision: 9});
  await f.controller.save("x".repeat(65));
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(f.runtime.session.inspectPerformance).toHaveBeenCalledTimes(2);
  expect(vi.mocked(f.runtime.session.inspectPerformance).mock.calls.map(([id]) => id))
    .toEqual([ids.performance, ids.performance]);
  expect(f.store.bind).toHaveBeenCalledOnce();
  expect(f.controller.getState().bindingStatus).toBe("bound");
});

test("Performance name preflight keeps an UNKNOWN name read-only and its original retry reachable", async () => {
  const f = controllerFixture();renderSurface(f);
  await act(() => f.controller.refreshRecovery());
  await act(() => f.controller.record());await act(() => f.controller.stop());
  selectPerformPage("Takes");
  fireEvent.change(screen.getByRole("textbox", {name: "Performance name"}),
    {target: {value: "Owned take"}});
  vi.mocked(f.runtime.session.savePerformance).mockRejectedValueOnce(Object.assign(
    new Error("reply lost"), {code: "HOST_TIMEOUT"}));
  vi.mocked(f.runtime.session.inspectPerformance).mockRejectedValueOnce(new Error("inspection unavailable"));
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("could not confirm the save"));
  const input = screen.getByRole("textbox", {name: "Performance name"});
  expect(input.hasAttribute("disabled"), "the admitted name owns the pending retry").toBe(true);
  expect((input as HTMLInputElement).value).toBe("Owned take");
  expect(screen.queryByText("Performance saved", {exact: true})).toBeNull();
  expect(screen.getByRole("button", {name: "Save Performance"}).hasAttribute("disabled")).toBe(false);
  vi.mocked(f.runtime.session.inspectPerformance).mockResolvedValueOnce({id: ids.performance,
    name: "Owned take", createdBpm: 120, recordingArtifact: null, events: [], projectRevision: 9});
  await userEvent.click(screen.getByRole("button", {name: "Save Performance"}));
  await waitFor(() => expect(f.controller.getState().bindingStatus).toBe("bound"));
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(f.runtime.session.inspectPerformance).toHaveBeenCalledTimes(2);
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

test("saved Take header reads wait for the complete managed WAV bind", async () => {
  const fixture = controllerFixture();
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  await fixture.controller.stop();
  const binding = deferred<{committedRevision: number}>();
  fixture.store.bind.mockReturnValueOnce(binding.promise);
  const saving = fixture.controller.save("Pending WAV");
  await vi.waitFor(() => expect(fixture.store.bind).toHaveBeenCalledTimes(1));
  const list = vi.mocked(fixture.runtime.session.listPerformances);
  list.mockClear();
  const refreshing = fixture.controller.refreshPerformances();
  try {
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(list, "recovery-capable list must not scavenge the unbound managed WAV")
      .not.toHaveBeenCalled();
  } finally {
    binding.resolve({committedRevision: 11});
    await Promise.all([saving, refreshing]);
  }
  expect(list).toHaveBeenCalled();
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
  disconnect();
});

test("managed WAV bind waits for older header reads without blocking unrelated mutations", async () => {
  const fixture = controllerFixture();
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  await fixture.controller.stop();
  const older = deferred<readonly PerformanceSummary[]>();
  const list = vi.mocked(fixture.runtime.session.listPerformances);
  list.mockReturnValueOnce(older.promise);
  const refreshing = fixture.controller.refreshPerformances();
  await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  const saving = fixture.controller.save("Older observer");
  await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(3));
  try {
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(fixture.runtime.session.savePerformance).toHaveBeenCalledOnce();
    expect(fixture.store.bind, "the older recovery-capable read must retire before installing WAV")
      .not.toHaveBeenCalled();
  } finally {
    older.resolve([]);
    await Promise.all([saving, refreshing]);
    disconnect();
  }
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
});

test("an acknowledged recovery discard preserves the pending WAV bind retry", async () => {
  const f = controllerFixture();
  await f.controller.refreshRecovery();await f.controller.record();await f.controller.stop();
  f.store.bind.mockRejectedValueOnce(Object.assign(new Error("bind busy"), {code: "PROJECT_BUSY"}));
  await f.controller.save("Retained WAV");
  const stopped = f.controller.getState().recording;
  const bindError = f.controller.getState().error;
  expect(stopped.wav).not.toBeNull();
  expect(bindError).toContain("Choose Retry WAV bind");
  const discard = vi.mocked(f.runtime.session.discardPerformanceRecovery);
  discard.mockImplementationOnce(async ({requestId, sessionId}) => ({requestId, sessionId,
    performanceId: ids.pattern1, state: "stopped", pendingEventCount: 0,
    replayed: false, projectRevision: null}));
  const list = vi.mocked(f.runtime.session.listPerformances);list.mockClear();
  await f.controller.discardRecovery(ids.pattern2);
  expect(discard).toHaveBeenCalledOnce();
  expect(discard).toHaveBeenCalledWith({sessionId: ids.pattern2, requestId: expect.any(String)});
  expect(f.controller.getState().recoveryStatus).toBe("discarded");
  expect(f.controller.getState().error,
    "a refused saved-list observation must not replace the acknowledged discard or WAV retry").toBe(bindError);
  expect(f.controller.getState().performancesStatus).toBe("unavailable");
  expect(list).not.toHaveBeenCalled();
  expect(f.controller.getState().recording).toEqual(stopped);
  expect(f.cleanupTemporary).not.toHaveBeenCalled();
  await f.controller.retryWavBind();
  expect(f.store.bind).toHaveBeenCalledTimes(2);
  expect(f.controller.getState().bindingStatus).toBe("bound");
  expect(f.controller.getState().recording.phase).toBe("idle");
  expect(list).toHaveBeenCalled();
  expect(discard).toHaveBeenCalledOnce();
});

test("a failed WAV bind keeps later list observers away from its retained managed bytes", async () => {
  const fixture = controllerFixture();
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  await fixture.controller.stop();
  fixture.store.bind.mockRejectedValueOnce(Object.assign(new Error("bind busy"), {code: "PROJECT_BUSY"}));
  await fixture.controller.save("Retained WAV");
  const list = vi.mocked(fixture.runtime.session.listPerformances);
  list.mockClear();
  await expect(fixture.controller.refreshPerformances()).rejects.toThrow("Bind or discard");
  expect(list).not.toHaveBeenCalled();
  await fixture.controller.retryWavBind();
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
  expect(list).toHaveBeenCalled();
  disconnect();
});

test("a rejected header peer does not retire the other read before managed WAV installation", async () => {
  const fixture = controllerFixture();
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  await fixture.controller.stop();
  const list = vi.mocked(fixture.runtime.session.listPerformances);
  const recovery = deferred<readonly never[]>();
  list.mockRejectedValueOnce(new Error("older list failed"));
  vi.mocked(fixture.runtime.session.listPerformanceRecovery).mockReturnValueOnce(recovery.promise);
  const observing = fixture.controller.refreshPerformances().catch(() => {});
  await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  const saving = fixture.controller.save("Pending recovery read");
  await vi.waitFor(() => expect(list).toHaveBeenCalledTimes(3));
  try {
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(fixture.store.bind, "one rejected peer does not retire the unfinished read")
      .not.toHaveBeenCalled();
  } finally {
    recovery.resolve([]);
    await Promise.all([observing, saving]);
    disconnect();
  }
  expect(fixture.controller.getState().bindingStatus).toBe("bound");
});

test("discard after a failed WAV bind releases its saved Take observation restriction", async () => {
  const fixture = controllerFixture();
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.record();
  await fixture.controller.stop();
  fixture.store.bind.mockRejectedValueOnce(Object.assign(new Error("bind busy"), {code: "PROJECT_BUSY"}));
  await fixture.controller.save("Discard retained WAV");
  await fixture.controller.discard();
  expect(fixture.store.discard).toHaveBeenCalledOnce();
  expect(fixture.controller.getState().recording.phase).toBe("idle");
  expect(fixture.controller.getState().performancesStatus).toBe("ready");
  disconnect();
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
  selectPerformPage("Takes");
  // Opening Takes now refreshes its saved list. Arm the failure only after
  // that far-side read so the original Save->list->retry-bind leg owns it.
  await waitFor(() => expect(fixture.controller.getState().performancesStatus).toBe("ready"));
  expect(fixture.runtime.session.listPerformances).toHaveBeenCalledTimes(2);
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockRejectedValueOnce(new Error("list failed"));

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
  // The stopped current recording is still unsaved. This separate saved Take
  // keeps the original replay/reset leg without presenting that draft as saved.
  const savedPerformanceId = ids.pattern2;
  (fixture.runtime.session.listPerformances as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{performanceId: savedPerformanceId, name: "Take 1",
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
  expect(fixture.runtime.session.beginPerformanceReplay).toHaveBeenCalledWith({
    replayId: expect.any(String), performanceId: savedPerformanceId,
  });
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
    .toBe("Recording session ended");
});

test.each([
  ["owner_lost", "Recording session ended"],
  ["/Users/private/unrecognized_reason", "Recording needs review"],
])("recovery card and status explain %s while retaining the raw candidate", async (reason, label) => {
  const fixture = controllerFixture();
  (fixture.runtime.session.listPerformanceRecovery as ReturnType<typeof vi.fn>)
    .mockResolvedValue([{sessionId: ids.session, performanceId: ids.performance,
      reason, durableEventCount: 1, pendingEventCount: 1, fingerprint: "f".repeat(64)}]);
  renderSurface(fixture);
  await fixture.controller.refreshRecovery();
  selectPerformPage("Replay");
  const region = screen.getByRole("group", {name: "Performance recovery"});
  expect(within(within(region).getByRole("article")).getByText(label)).toBeTruthy();
  expect(region.textContent).not.toContain(reason);
  expect(screen.getByRole("status", {name: "Performance recovery status"}).textContent).toBe(label);
  expect(fixture.controller.getState().recovery[0]?.reason).toBe(reason);
  expect(within(region).getByRole("button", {name: "Apply recovery"})).toBeTruthy();
  expect(within(region).getByRole("button", {name: "Discard recovery"})).toBeTruthy();
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
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
  const filter = screen.getByRole("slider", {name: "Stutter"});
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
  expect(screen.getByRole("button", {name: "MORE"}).getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByRole("slider", {name: "Stutter"})).toBeTruthy();
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
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
  expect(Object.values(current!.bindings).map((binding) => binding.label)).toEqual(["Crush", "Stutter", "Gate"]);
  act(() => current!.bindings[1]!.onTurn(2));
  expect(fixture.controller.getState().fx.crush).toBe(520);
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
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


// This is a component storage/capture model with real Controller, WAV writer
// and recording Store. Its receipts are not production OPFS/Native/physical proof.
async function shutdownRecordingFixture() {
  const runtime = sessionFixture();
  let temporaryPresent = true;
  let bytes = new Uint8Array(0);
  let writerOwned = false;
  let captureOwned = false;
  let coreOwned = false;
  let coreRecordState: "idle" | "active" | "stopped" = "idle";
  let nextCheckpoint: Promise<void> | null = null;
  let abortFailure: {error: unknown} | null = null;
  let checkpointEntered = false;
  const abort = vi.fn(async () => {
    if (abortFailure !== null) throw abortFailure.error;
    writerOwned = false;
  });
  let sink: Parameters<CreatorPerformanceRuntimeSession["startPerformanceMasterCapture"]>[0] | null = null;
  const truth = {revision: 7, name: null as string | null, artifact: null as unknown};
  const file = {
    name: `${ids.performance}.wav`,
    async createWritable({keepExistingData = false} = {}) {
      if (writerOwned) throw new Error("The original modeled writer still owns its transaction");
      writerOwned = true;
      let pending = keepExistingData ? bytes.slice() : new Uint8Array(0);
      let cursor = 0;
      return {
        async seek(position: number) { cursor = position; },
        async write(data: Uint8Array) {
          const next = new Uint8Array(Math.max(pending.length, cursor + data.length));
          next.set(pending); next.set(data, cursor); pending = next; cursor += data.length;
        },
        async truncate(length: number) {
          const next = new Uint8Array(length);
          next.set(pending.subarray(0, length)); pending = next;
        },
        async close() {
          if (nextCheckpoint !== null) {
            const original = nextCheckpoint; nextCheckpoint = null;
            checkpointEntered = true;
            await original;
          }
          bytes = pending; writerOwned = false;
        },
        abort,
      };
    },
    async getFile() {
      if (!temporaryPresent) throw new Error("The original temporary has been deleted");
      const snapshot = bytes.slice();
      return {size: snapshot.length, type: "audio/wav",
        slice(start = 0, end = snapshot.length) {
          return {arrayBuffer: async () => snapshot.slice(start, end).buffer};
        }};
    },
  };
  const cleanupTemporary = vi.fn(async () => {
    if (writerOwned || captureOwned) throw new Error("Cannot delete live original capture/writer bytes");
    temporaryPresent = false;
  });
  const installed = new Map<string, Uint8Array>();
  const storage = {
    installManaged: vi.fn(async (artifact: {sha256: string}) => {
      installed.set(artifact.sha256, bytes.slice());
      return {name: `${artifact.sha256}.wav`};
    }),
    deleteTemporary: cleanupTemporary,
  };
  const writer = await openWavStreamWriter(file, {
    perform_recording_frames: 86_400_000, perform_recording_queue_batches: 32,
  });
  const bind = vi.fn<CreatorPerformanceRuntimeSession["bindPerformanceRecording"]>(async (request) => {
    truth.artifact = request.recordingArtifact; truth.revision = 11;
    return {performanceId: ids.performance, committedRevision: 11,
      replayed: false, projectRevision: 11};
  });
  runtime.session.bindPerformanceRecording = bind;
  const discard = runtime.session.discardPerformance as ReturnType<typeof vi.fn>;
  discard.mockImplementation(async () => {
    truth.name = null; truth.artifact = null; truth.revision = 11;
    return {committedRevision: 11};
  });
  const save = runtime.session.savePerformance as ReturnType<typeof vi.fn>;
  save.mockImplementation(async (request) => {
    truth.name = request.name; truth.revision = 10;
    return {performanceId: ids.performance, committedRevision: 10, replayed: false, projectRevision: 10};
  });
  const inspect = runtime.session.inspectPerformance as ReturnType<typeof vi.fn>;
  inspect.mockImplementation(async () => ({id: ids.performance, name: truth.name,
    projectRevision: truth.revision, recordingArtifact: truth.artifact, events: []}));
  runtime.calls.begin.mockImplementation(async () => {
    coreOwned = true; coreRecordState = "active"; truth.revision = 8;
    return {performanceId: ids.performance, committedRevision: 8, replayed: false, projectRevision: 8};
  });
  runtime.calls.stop.mockImplementation(async () => {
    coreOwned = false; coreRecordState = "stopped";
    return {requestId: "stop", sessionId: ids.session, performanceId: ids.performance,
      state: "stopped" as const, pendingEventCount: 0, replayed: false, projectRevision: null};
  });
  // Successful raw events refresh this authoring status. This complete reply
  // models the original begin/Stop operations, not an owner retirement receipt.
  (runtime.session.queryPerformanceRecordingStatus as ReturnType<typeof vi.fn>)
    .mockImplementation(async () => authority({state: coreRecordState,
      sessionId: coreRecordState === "idle" ? null : ids.session,
      performanceId: coreRecordState === "idle" ? null : ids.performance}));
  const captureStop = vi.fn(async () => { captureOwned = false; sink?.onStopped(); });
  const startCapture = vi.fn<CreatorPerformanceRuntimeSession["startPerformanceMasterCapture"]>(
    async (capturing): Promise<PerformanceMasterCapture> => {
      sink = capturing; captureOwned = true;
      return {stop: captureStop};
    });
  runtime.session.startPerformanceMasterCapture = startCapture;
  const store = new PerformanceRecordingStore(file, storage, runtime.session);
  const refresh = vi.fn(async () => ({revision: truth.revision}));
  const reports = vi.fn();
  let sequence = 0;
  const controller = createPerformController({session: runtime.session,
    getCreatorState: () => creatorState(), refreshProject: refresh,
    reportFailure: reports, opfsAvailable: () => true,
    dependencies: {
      createId: () => [ids.session, ids.performance][sequence++] ?? `shutdown-${sequence}`,
      prepareRecording: async () => ({writer, store, cleanupTemporary}),
    }});
  await controller.refreshRecovery();
  return {runtime: {...runtime, calls: {...runtime.calls, capture: startCapture}},
    controller, file, writer, store, storage, captureStop,
    cleanupTemporary, bind, discard, save, inspect, refresh, reports, truth, installed,
    temporaryPresent: () => temporaryPresent,
    bytes: () => bytes.slice(), writerOwned: () => writerOwned,
    captureOwned: () => captureOwned, coreOwned: () => coreOwned,
    getSink: () => sink, abort,
    holdNextCheckpoint: (original: Promise<void>) => { nextCheckpoint = original; },
    rejectAbort: (error: unknown) => { abortFailure = {error}; },
    checkpointEntered: () => checkpointEntered,
  };
}

function modeledCleanupSession(session: CreatorPerformanceRuntimeSession) {
  const listeners = new Set<(value: RuntimeHostState) => void>();
  let diagnostics = {state: "audio-suspended", error_code: null, error_details: {},
    capabilities: {opfs: true, opfsWritableReplace: true}} as unknown as RuntimeDiagnostics;
  const independentCleanup = deferred<boolean>();
  const wait = vi.fn(() => independentCleanup.promise);
  const close = vi.fn(async () => false);
  const modeled = Object.assign(session, {
    start: vi.fn(async () => true), close, waitForTerminalCleanup: wait,
    diagnostics: () => diagnostics,
    subscribeHostState(listener: (value: RuntimeHostState) => void) {
      listeners.add(listener); return () => listeners.delete(listener);
    },
    subscribeDiagnostics: () => () => {},
  });
  return {session: modeled, independentCleanup, wait, close,
    emit(state: string) {
      diagnostics = {...diagnostics, state, error_code: "HOST_TIMEOUT"};
      for (const listener of [...listeners]) listener({state, errorCode: "HOST_TIMEOUT",
        errorDetails: {reason: "independent modeled SDK fatal"}});
    },
  };
}

function PerformShutdownBoundary({barrier}: {barrier: () => Promise<void>}) {
  const runtime = useRuntime();
  useEffect(() => runtime.registerShutdownBarrier(barrier), [runtime.registerShutdownBarrier, barrier]);
  return <>
    <output aria-label="shutdown-provider-phase">{runtime.phase}</output>
    <button type="button" onClick={runtime.retryRuntime}>Retry failed Perform Runtime</button>
  </>;
}

function mountPerformShutdown(fixture: {controller: ReturnType<typeof createPerformController>;
  runtime: {session: CreatorPerformanceRuntimeSession}}) {
  const old = modeledCleanupSession(fixture.runtime.session);
  const next = modeledCleanupSession(sessionFixture().session);
  const sessions = [old.session, next.session];
  let creations = 0;
  const factory = vi.fn(() => sessions[creations++]!);
  // Exact actual controller.close is the registered producer; no synthetic reject.
  const barrier = vi.fn(() => fixture.controller.close());
  const rendered = render(<RuntimeProvider factory={factory}>
    <PerformShutdownBoundary barrier={barrier} />
  </RuntimeProvider>);
  return {old, next, factory, barrier, rendered};
}

function triggerPerformReplacement(harness: ReturnType<typeof mountPerformShutdown>, mode: "manual" | "automatic") {
  act(() => harness.old.emit(mode === "automatic" ? "restart-required" : "failed"));
  if (mode === "manual") fireEvent.click(screen.getByRole("button", {name: "Retry failed Perform Runtime"}));
}

for (const mode of ["manual", "automatic"] as const) {
  for (const stage of ["core-stop", "capture-stop"] as const) {
    test(`${mode} Provider blocks replacement after the original Perform ${stage} fails despite independent positive modeled SDK cleanup`, async () => {
      const fixture = await shutdownRecordingFixture();
      await fixture.controller.record();
      const originalBytes = fixture.bytes();
      const originalTruth = {...fixture.truth};
      const original = new Error(`original ${stage} failure`);
      const gate = deferred<void>();
      if (stage === "core-stop") fixture.runtime.calls.stop.mockImplementationOnce(async () => {
        await gate.promise;
        throw original;
      });
      else fixture.captureStop.mockImplementationOnce(async () => {
        await gate.promise;
        throw original;
      });
      const harness = mountPerformShutdown(fixture);
      await screen.findByText("ready");
      harness.old.independentCleanup.resolve(true);
      expect(await harness.old.independentCleanup.promise).toBe(true);
      triggerPerformReplacement(harness, mode);
      await waitFor(() => expect(stage === "core-stop" ? fixture.runtime.calls.stop : fixture.captureStop)
        .toHaveBeenCalledTimes(1));
      expect(harness.factory).toHaveBeenCalledTimes(1);
      expect(fixture.temporaryPresent()).toBe(true);
      await act(async () => { gate.resolve(); await gate.promise; });
      await expect(fixture.controller.close()).rejects.toBe(original);
      await act(async () => {});
      const originalClose = harness.barrier.mock.results[0]?.value;
      expect(fixture.controller.close()).toBe(originalClose);
      expect(harness.factory).toHaveBeenCalledTimes(1);
      expect(harness.old.wait).not.toHaveBeenCalled();
      expect(harness.old.close).not.toHaveBeenCalled();
      expect(fixture.controller.getState().recording.phase).toBe("stopped");
      expect(fixture.controller.getState().recording.sessionId).toBe(ids.session);
      expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
      expect(fixture.bytes()).toEqual(originalBytes);
      expect(fixture.truth).toEqual(originalTruth);
      expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
      expect(fixture.reports).toHaveBeenCalledWith("Perform", original);
      // Unrelated save/discard cannot delete the still-unsettled exact owner.
      await fixture.controller.save("Unrelated retry");
      await fixture.controller.discard();
      expect(fixture.bind).not.toHaveBeenCalled();
      expect(fixture.discard).not.toHaveBeenCalled();
      expect(fixture.temporaryPresent()).toBe(true);
      expect(fixture.coreOwned()).toBe(stage === "core-stop");
      expect(fixture.captureOwned()).toBe(stage === "capture-stop");
    });
  }
}

for (const stage of ["bind", "discard", "save-unknown"] as const) {
  test(`real Perform ${stage} retained failure reaches the registered barrier and prevents automatic replacement`, async () => {
    const fixture = await shutdownRecordingFixture();
    await fixture.controller.record();
    await fixture.controller.stop();
    const original = new Error(`original ${stage} storage failure`);
    const gate = deferred<never>();
    if (stage === "bind") fixture.bind.mockImplementationOnce(() => gate.promise);
    else if (stage === "discard") fixture.discard.mockImplementationOnce(() => gate.promise);
    else {
      fixture.save.mockImplementationOnce(() => gate.promise);
      fixture.inspect.mockRejectedValueOnce(new Error("later readback also unavailable"));
    }
    const originalBytes = fixture.bytes();
    const operation = stage === "discard" ? fixture.controller.discard() : fixture.controller.save("Original Take");
    await waitFor(() => expect(stage === "bind" ? fixture.bind : stage === "discard" ? fixture.discard : fixture.save)
      .toHaveBeenCalledTimes(1));
    const retainedTruth = {...fixture.truth};
    const harness = mountPerformShutdown(fixture);
    await screen.findByText("ready");
    harness.old.independentCleanup.resolve(true);
    expect(await harness.old.independentCleanup.promise).toBe(true);
    triggerPerformReplacement(harness, "automatic");
    await waitFor(() => expect(harness.barrier).toHaveBeenCalledTimes(1));
    expect(harness.factory).toHaveBeenCalledTimes(1);
    expect(fixture.temporaryPresent()).toBe(true);
    await act(async () => { gate.reject(original); await operation; });
    await expect(fixture.controller.close()).rejects.toBe(original);
    await act(async () => {});
    expect(harness.factory).toHaveBeenCalledTimes(1);
    expect(fixture.controller.close()).toBe(harness.barrier.mock.results[0]?.value);
    expect(harness.old.wait).not.toHaveBeenCalled();
    expect(fixture.bytes()).toEqual(originalBytes);
    expect(fixture.file.name).toBe(`${ids.performance}.wav`);
    expect(fixture.truth).toEqual(retainedTruth);
    expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
    expect(fixture.temporaryPresent()).toBe(true);
    expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
    expect(fixture.coreOwned()).toBe(false);
    expect(fixture.captureOwned()).toBe(false);
    expect(fixture.writerOwned()).toBe(false);
  });
}

test("unknown original Core begin retains exact bytes and original error through the real manual Provider barrier", async () => {
  const fixture = await shutdownRecordingFixture();
  const original = new Error("original begin response lost");
  const admitBegin = fixture.runtime.calls.begin.getMockImplementation()!;
  fixture.runtime.calls.begin.mockImplementationOnce(async () => {
    await admitBegin();
    throw original;
  });
  await fixture.controller.record();
  const bytes = fixture.bytes();
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  expect(await harness.old.independentCleanup.promise).toBe(true);
  triggerPerformReplacement(harness, "manual");
  await expect(fixture.controller.close()).rejects.toBe(original);
  await act(async () => {});
  expect(harness.factory).toHaveBeenCalledTimes(1);
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.writerOwned()).toBe(false);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(fixture.bytes()).toEqual(bytes);
  expect(fixture.controller.getState().recording.expectedRevision).toBeNull();
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
  expect(fixture.coreOwned()).toBe(true); // Original begin was actually admitted in this component model.
  expect(fixture.truth.revision).toBe(8);
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
});

test("setup interrupted before Core submission closes actual capture/WAV and temporary before replacement", async () => {
  const fixture = await shutdownRecordingFixture();
  const captureGate = deferred<Awaited<ReturnType<CreatorPerformanceRuntimeSession["startPerformanceMasterCapture"]>>>();
  fixture.runtime.calls.capture.mockImplementationOnce(() => captureGate.promise);
  const starting = fixture.controller.record();
  await waitFor(() => expect(fixture.runtime.calls.capture).toHaveBeenCalledTimes(1));
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  triggerPerformReplacement(harness, "automatic");
  await waitFor(() => expect(harness.barrier).toHaveBeenCalledTimes(1));
  expect(harness.factory).toHaveBeenCalledTimes(1);
  const queue = fixture.controller.recordingSink();
  expect(queue).not.toBeNull();
  captureGate.resolve({stop: vi.fn(async () => queue!.onStopped())});
  await starting;
  await expect(fixture.controller.close()).resolves.toBeUndefined();
  await waitFor(() => expect(harness.factory).toHaveBeenCalledTimes(2));
  expect(await harness.old.independentCleanup.promise).toBe(true);
  expect(harness.old.wait).toHaveBeenCalledTimes(1);
  expect(fixture.runtime.calls.begin).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
  expect(fixture.writerOwned()).toBe(false);
  expect(fixture.cleanupTemporary).toHaveBeenCalledTimes(1);
  expect(fixture.temporaryPresent()).toBe(false);
  expect(fixture.controller.getState().recording.phase).toBe("idle");
  expect(fixture.reports).toHaveBeenCalledWith("Perform",
    expect.objectContaining({message: "Performance controller closed during setup"}));
});

test("the same acknowledged bind cleanup retry clears only its real retained debt before clean close", async () => {
  const fixture = await shutdownRecordingFixture();
  await fixture.controller.record();
  await fixture.controller.stop();
  const original = new Error("original temporary deletion failed");
  fixture.cleanupTemporary.mockRejectedValueOnce(original);
  await fixture.controller.save("Matching Take");
  expect(fixture.bind).toHaveBeenCalledTimes(1);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(fixture.controller.getState().bindingStatus).toBe("retry");
  await fixture.controller.retryWavBind();
  expect(fixture.bind).toHaveBeenCalledTimes(1);
  expect(fixture.cleanupTemporary).toHaveBeenCalledTimes(2);
  expect(fixture.temporaryPresent()).toBe(false);
  expect(fixture.truth.name).toBe("Matching Take");
  expect(fixture.truth.artifact).not.toBeNull();
  await expect(fixture.controller.close()).resolves.toBeUndefined();
});

test("a committed bind's display failure alone is not unresolved application shutdown ownership", async () => {
  const fixture = await shutdownRecordingFixture();
  await fixture.controller.record();
  await fixture.controller.stop();
  const commitBind = fixture.bind.getMockImplementation()!;
  fixture.bind.mockImplementationOnce(async (request) => {
    const receipt = await commitBind(request);
    fixture.refresh.mockRejectedValueOnce(new Error("display projection unavailable"));
    return receipt;
  });
  await fixture.controller.save("Display Only Failure");
  expect(fixture.temporaryPresent()).toBe(false);
  expect(fixture.controller.getState().bindingStatus).toBe("retry");
  await expect(fixture.controller.close()).resolves.toBeUndefined();
  expect(fixture.writerOwned()).toBe(false);
  expect(fixture.captureOwned()).toBe(false);
  expect(fixture.coreOwned()).toBe(false);
});


test("original setup projection and failed real discard preserve exact errors and bytes at the Provider barrier", async () => {
  const fixture = await shutdownRecordingFixture();
  const primary = new Error("original setup projection failed");
  const compensation = new Error("original discard response failed");
  const gate = deferred<never>();
  fixture.refresh.mockRejectedValueOnce(primary);
  fixture.discard.mockImplementationOnce(() => gate.promise);
  const starting = fixture.controller.record();
  await waitFor(() => expect(fixture.discard).toHaveBeenCalledTimes(1));
  const retainedBytes = fixture.bytes();
  const retainedTruth = {...fixture.truth};
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  expect(await harness.old.independentCleanup.promise).toBe(true);
  triggerPerformReplacement(harness, "automatic");
  await waitFor(() => expect(harness.barrier).toHaveBeenCalledTimes(1));
  expect(harness.factory).toHaveBeenCalledTimes(1);
  await act(async () => { gate.reject(compensation); await starting; });
  await expect(fixture.controller.close()).rejects.toBe(primary);
  await act(async () => {});
  expect(harness.factory).toHaveBeenCalledTimes(1);
  expect(fixture.controller.close()).toBe(harness.barrier.mock.results[0]?.value);
  expect(fixture.reports).toHaveBeenCalledWith("Perform", primary);
  expect(fixture.reports).toHaveBeenCalledWith("Perform", compensation);
  expect(fixture.bytes()).toEqual(retainedBytes);
  expect(fixture.truth).toEqual(retainedTruth);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.expectedRevision).toBe(8);
  expect(fixture.controller.getState().recording.sessionId).toBe(ids.session);
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
});

test("a trusted default preparation failure before any writer attempt does not latch shutdown failure", async () => {
  const runtime = sessionFixture();
  const previousStorage = navigator.storage;
  Object.defineProperty(navigator, "storage", {configurable: true, value: undefined});
  const reports = vi.fn();
  const controller = createPerformController({session: runtime.session,
    getCreatorState: () => creatorState(), refreshProject: async () => {},
    opfsAvailable: () => true, reportFailure: reports});
  try {
    await controller.refreshRecovery();
    await controller.record();
    expect(reports).toHaveBeenCalledWith("Perform",
      expect.objectContaining({message: "Origin-private storage is unavailable"}));
    expect(runtime.calls.capture).not.toHaveBeenCalled();
    expect(runtime.calls.begin).not.toHaveBeenCalled();
    expect(controller.getState().recording.phase).toBe("idle");
    const harness = mountPerformShutdown({controller, runtime});
    await screen.findByText("ready");
    harness.old.independentCleanup.resolve(true);
    triggerPerformReplacement(harness, "manual");
    await expect(controller.close()).resolves.toBeUndefined();
    await waitFor(() => expect(harness.factory).toHaveBeenCalledTimes(2));
    expect(await harness.old.independentCleanup.promise).toBe(true);
    expect(harness.old.wait).toHaveBeenCalledTimes(1);
  } finally {
    Object.defineProperty(navigator, "storage", {configurable: true, value: previousStorage});
  }
});

test("a late matching cleanup retry cannot rewrite the original cached rejected close or permit a factory", async () => {
  const fixture = await shutdownRecordingFixture();
  await fixture.controller.record();
  await fixture.controller.stop();
  const original = new Error("original temporary cleanup rejected");
  fixture.cleanupTemporary.mockRejectedValueOnce(original);
  await fixture.controller.save("Retained Take");
  const pendingError = fixture.reports.mock.calls.find((call) =>
    (call[1] as {cause?: unknown} | undefined)?.cause === original)?.[1];
  expect(pendingError).toBeDefined();
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  triggerPerformReplacement(harness, "automatic");
  await expect(fixture.controller.close()).rejects.toBe(pendingError);
  const cached = fixture.controller.close();
  await fixture.controller.retryWavBind();
  expect(fixture.temporaryPresent()).toBe(false);
  expect(fixture.bind).toHaveBeenCalledTimes(1);
  expect(fixture.controller.close()).toBe(cached);
  await expect(cached).rejects.toBe(pendingError);
  fireEvent.click(screen.getByRole("button", {name: "Retry failed Perform Runtime"}));
  await act(async () => {});
  expect(await harness.old.independentCleanup.promise).toBe(true);
  expect(harness.factory).toHaveBeenCalledTimes(1);
});


test("the original real WAV checkpoint holds the registered Perform barrier until durable PCM completion", async () => {
  const fixture = await shutdownRecordingFixture();
  await fixture.controller.record();
  const original = deferred<void>();
  fixture.holdNextCheckpoint(original.promise);
  fixture.getSink()!.onBatch([new Float32Array([0.25, -0.25]), new Float32Array([0.5, -0.5])]);
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  triggerPerformReplacement(harness, "automatic");
  await waitFor(() => expect(fixture.checkpointEntered()).toBe(true));
  let settled = false;
  const close = fixture.controller.close();
  void close.then(() => { settled = true; });
  await act(async () => {});
  expect(settled).toBe(false);
  expect(fixture.writerOwned()).toBe(true);
  expect(fixture.bytes()).toHaveLength(44);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(harness.factory).toHaveBeenCalledTimes(1);
  expect(harness.old.close).not.toHaveBeenCalled();
  expect(harness.old.wait).not.toHaveBeenCalled();
  await act(async () => { original.resolve(); await close; });
  await waitFor(() => expect(harness.factory).toHaveBeenCalledTimes(2));
  expect(fixture.writer.snapshot).toMatchObject({state: "sealed", reason: "stopped", durableFrames: 2});
  expect(fixture.bytes()).toHaveLength(52);
  expect(new DataView(fixture.bytes().buffer).getUint32(40, true)).toBe(8);
  expect(fixture.writerOwned()).toBe(false);
  expect(fixture.captureOwned()).toBe(false);
  expect(fixture.coreOwned()).toBe(false);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
  expect(fixture.truth).toEqual({revision: 8, name: null, artifact: null});
  expect(harness.old.close).toHaveBeenCalledTimes(1);
  expect(harness.old.wait).toHaveBeenCalledTimes(1);
});

test("a real Queue writer-error snapshot cannot erase the failed original writable abort or permit replacement", async () => {
  const fixture = await shutdownRecordingFixture();
  await fixture.controller.record();
  const checkpoint = deferred<void>();
  const checkpointFailure = new Error("original writable checkpoint failed");
  const abortFailure = new Error("original writable abort failed and still owns its transaction");
  fixture.holdNextCheckpoint(checkpoint.promise);
  fixture.rejectAbort(abortFailure);
  fixture.getSink()!.onBatch([new Float32Array([0.25, -0.25]), new Float32Array([0.5, -0.5])]);
  const harness = mountPerformShutdown(fixture);
  await screen.findByText("ready");
  harness.old.independentCleanup.resolve(true);
  triggerPerformReplacement(harness, "automatic");
  await waitFor(() => expect(fixture.checkpointEntered()).toBe(true));
  expect(harness.factory).toHaveBeenCalledTimes(1);
  expect(fixture.writerOwned()).toBe(true);
  const close = fixture.controller.close();
  // Observe the original cached Promise before releasing the real storage operation.
  void close.catch(() => {});
  await act(async () => { checkpoint.reject(checkpointFailure); });
  await waitFor(() => expect(fixture.reports.mock.calls.some(([, error]) =>
    (error as {reason?: string} | undefined)?.reason === "writer-error")).toBe(true));
  const realQueueFailure = fixture.reports.mock.calls.find(([, error]) =>
    (error as {reason?: string} | undefined)?.reason === "writer-error")![1];
  expect(Object.isFrozen(realQueueFailure)).toBe(true);
  await expect(close).rejects.toBe(realQueueFailure);
  expect(fixture.abort).toHaveBeenCalledTimes(1);
  expect(fixture.abort).toHaveBeenCalledWith(checkpointFailure);
  expect(fixture.writer.snapshot).toMatchObject({state: "sealed", reason: "writer-error", durableFrames: 0});
  expect(fixture.writerOwned()).toBe(true);
  expect(fixture.captureOwned()).toBe(false);
  expect(fixture.coreOwned()).toBe(false);
  expect(fixture.bytes()).toHaveLength(44);
  expect(fixture.temporaryPresent()).toBe(true);
  expect(fixture.controller.getState().recording.wav?.reason).toBe("writer-error");
  expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
  await fixture.controller.save("Do not delete the original owner");
  await fixture.controller.discard();
  expect(fixture.save).not.toHaveBeenCalled();
  expect(fixture.bind).not.toHaveBeenCalled();
  expect(fixture.discard).not.toHaveBeenCalled();
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.truth).toEqual({revision: 8, name: null, artifact: null});
  expect(fixture.controller.close()).toBe(close);
  expect(await harness.old.independentCleanup.promise).toBe(true);
  expect(harness.old.close).not.toHaveBeenCalled();
  expect(harness.old.wait).not.toHaveBeenCalled();
  expect(harness.factory).toHaveBeenCalledTimes(1);
  // The real writer currently hides abortFailure; this test does not invent its
  // missing channel or claim that the live writable/physical owner was released.
});


for (const operation of ["raw-event", "flush"] as const) {
  test(`an unrelated later ${operation} command cannot discharge the original unknown recording operation`, async () => {
    const fixture = await shutdownRecordingFixture();
    await fixture.controller.record();
    const original = new Error(`original ${operation} response lost`);
    if (operation === "raw-event") {
      fixture.runtime.calls.raw.mockRejectedValueOnce(original);
      await expect(fixture.controller.recordRawEvent({kind: "hold_on"})).rejects.toBe(original);
      await fixture.controller.recordRawEvent({kind: "hold_off"});
      expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(2);
    } else {
      fixture.runtime.calls.flush.mockRejectedValueOnce(original);
      await fixture.controller.flush();
      await fixture.controller.flush();
      expect(fixture.runtime.calls.flush).toHaveBeenCalledTimes(2);
    }
    await fixture.controller.stop();
    expect(fixture.coreOwned()).toBe(false);
    expect(fixture.captureOwned()).toBe(false);
    expect(fixture.writerOwned()).toBe(false);
    const harness = mountPerformShutdown(fixture);
    await screen.findByText("ready");
    harness.old.independentCleanup.resolve(true);
    triggerPerformReplacement(harness, "automatic");
    await expect(fixture.controller.close()).rejects.toBe(original);
    await act(async () => {});
    expect(await harness.old.independentCleanup.promise).toBe(true);
    expect(harness.factory).toHaveBeenCalledTimes(1);
    expect(fixture.controller.getState().recording.sessionId).toBe(ids.session);
    expect(fixture.controller.getState().recording.performanceId).toBe(ids.performance);
    expect(fixture.temporaryPresent()).toBe(true);
    expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  });
}


test("reserves Perform presses and physical release before the first receipt and submits in order", async () => {
  const fixture = controllerFixture();
  const firstReceipt = deferred<Awaited<ReturnType<typeof fixture.runtime.calls.raw>>>();
  fixture.runtime.calls.raw.mockReturnValueOnce(firstReceipt.promise);
  const view = renderSurface(fixture);
  const firstKey = Object.freeze({});
  const secondKey = Object.freeze({});
  let pending: Promise<void>[] = [];
  try {
    await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
    await fixture.controller.record();
    pending = [
      fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "physical-first",
        slot: 0, velocity: 100}, firstKey),
      fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "physical-second",
        slot: 0, velocity: 100}, secondKey),
      fixture.controller.recordRawEvent({kind: "pad_release", gestureId: "physical-first",
        slot: 0}, firstKey),
    ];
    // These are real Perform-controller calls into the Session double, not
    // proof of the SDK's aggregate ledger or Native/durable completion.
    expect(fixture.runtime.calls.prepare).toHaveBeenCalledTimes(3);
    expect(fixture.runtime.calls.prepare.mock.calls.map(([, key]) => key))
      .toEqual([firstKey, secondKey, firstKey]);
    expect(fixture.runtime.calls.prepare.mock.calls.map(([request]) => request.sessionId))
      .toEqual([ids.session, ids.session, ids.session]);
    expect(fixture.runtime.calls.prepare.mock.calls.map(([request]) => request.event.kind))
      .toEqual(["pad_press", "pad_press", "pad_release"]);
    await act(async () => {});
    expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(1);
    firstReceipt.resolve({eventId: "first", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    await Promise.all(pending);
    expect(fixture.runtime.calls.raw.mock.calls.map(([, key]) => key))
      .toEqual([firstKey, secondKey, firstKey]);
    await fixture.controller.stop();
    expect(fixture.controller.getState().recording.phase).toBe("stopped");
  } finally {
    firstReceipt.resolve({eventId: "first", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    await Promise.all(pending.map(operation => operation.catch(() => {})));
    view.unmount();
  }
});

test("Stop retains the original journal owner and waits for its matching release before finalizing", async () => {
  const fixture = controllerFixture();
  const pressReceipt = deferred<Awaited<ReturnType<typeof fixture.runtime.calls.raw>>>();
  const releaseReceipt = deferred<Awaited<ReturnType<typeof fixture.runtime.calls.raw>>>();
  fixture.runtime.calls.raw.mockReturnValueOnce(pressReceipt.promise)
    .mockReturnValueOnce(releaseReceipt.promise);
  const view = renderSurface(fixture);
  const physicalKey = Object.freeze({});
  let press: Promise<void> | undefined;
  let stopping: Promise<void> | undefined;
  try {
    await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
    await fixture.controller.record();
    press = fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "original-owner",
      slot: 3, velocity: 100}, physicalKey);
    stopping = fixture.controller.stop();
    expect(fixture.runtime.calls.prepare).toHaveBeenCalledTimes(2);
    const [submittedPress, submittedRelease] = fixture.runtime.calls.prepare.mock.calls;
    expect(submittedPress?.[1]).toBe(physicalKey);
    // Synthetic Stop may join the SDK's original (Session, gestureId) owner
    // mapping without a second physical-key argument; never invent an owner.
    expect(submittedRelease?.[0]).toMatchObject({sessionId: submittedPress?.[0].sessionId,
      event: {kind: "pad_release", gestureId: "original-owner", slot: 3}});
    expect(fixture.controller.getState().recording.phase).toBe("stopping");
    expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
    expect(fixture.captureStop).not.toHaveBeenCalled();
    pressReceipt.resolve({eventId: "press", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    await press;
    await act(async () => {});
    expect(fixture.runtime.calls.raw).toHaveBeenCalledTimes(2);
    expect(fixture.runtime.calls.stop).not.toHaveBeenCalled();
    releaseReceipt.resolve({eventId: "release", acceptedTick: 2, inputSequence: 2,
      coalesced: false, replayed: false, projectRevision: null});
    await stopping;
    expect(fixture.runtime.calls.stop).toHaveBeenCalledTimes(1);
    expect(fixture.runtime.calls.stop.mock.calls[0]?.[0]).toMatchObject({sessionId: ids.session});
    expect(fixture.captureStop).toHaveBeenCalledTimes(1);
    expect(fixture.order.indexOf("core-stop")).toBeLessThan(fixture.order.indexOf("capture-stop"));
    expect(fixture.order.indexOf("capture-stop")).toBeLessThan(fixture.order.indexOf("tail-drained"));
    expect(fixture.controller.getState().recording).toMatchObject({phase: "stopped",
      wav: {state: "sealed", durableFrames: 100, reason: "stopped"}});
  } finally {
    pressReceipt.resolve({eventId: "press", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    releaseReceipt.resolve({eventId: "release", acceptedTick: 2, inputSequence: 2,
      coalesced: false, replayed: false, projectRevision: null});
    await press?.catch(() => {});
    await stopping?.catch(() => {});
    view.unmount();
  }
});

test("observes a later SDK reservation refusal while an earlier Perform receipt is still held", async () => {
  const fixture = controllerFixture();
  const firstReceipt = deferred<Awaited<ReturnType<typeof fixture.runtime.calls.raw>>>();
  const original = new Error("second SDK admission rejected before first receipt");
  fixture.runtime.calls.raw.mockReturnValueOnce(firstReceipt.promise);
  const prepare = fixture.runtime.calls.prepare.getMockImplementation()!;
  fixture.runtime.calls.prepare.mockImplementationOnce(prepare)
    .mockImplementationOnce(() => { throw original; });
  const view = renderSurface(fixture);
  let first: Promise<void> | undefined;
  let rejected: Promise<unknown> | undefined;
  try {
    await waitFor(() => expect(fixture.controller.canRecord()).toBe(true));
    await fixture.controller.record();
    first = fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "held-first",
      slot: 0, velocity: 100}, Object.freeze({}));
    rejected = fixture.controller.recordRawEvent({kind: "pad_press", gestureId: "rejected-second",
      slot: 1, velocity: 100}, Object.freeze({})).then(() => null, error => error);
    expect(fixture.runtime.calls.prepare).toHaveBeenCalledTimes(2);
    // Leave one ordinary event-loop turn with the first receipt still held.
    // Vitest's unhandled-rejection check must remain clean: observing this
    // SDK reservation refusal cannot wait for the ordered tail to drain.
    await new Promise(resolve => setTimeout(resolve, 0));
    firstReceipt.resolve({eventId: "first", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    await first;
    expect(await rejected).toBe(original);
    // #1680: the public rejection retains the original error, while the
    // surface projects the existing catalogue message for an untyped error.
    expect(fixture.controller.getState().error).toBe(
      "Something went wrong in Creator. Try again. Details are in Developer diagnostics.",
    );
  } finally {
    firstReceipt.resolve({eventId: "first", acceptedTick: 1, inputSequence: 1,
      coalesced: false, replayed: false, projectRevision: null});
    await first?.catch(() => {});
    await rejected;
    view.unmount();
  }
});


test("real SDK admission preserves the interleaved Perform FX release after a held move", async () => {
  // Integration boundary: Creator's existing recording/Store/capture fixture
  // stays modeled. Only raw input admission and status reads use the REAL SDK;
  // no input queue or shared-gesture algorithm is reproduced by this test.
  // The SDK is not bootstrapped: no Runtime/Core/audio lifecycle is claimed.
  type WireEvent = {
    kind: string; gesture_id?: string; fx?: string; value?: number;
    slot?: number; velocity?: number;
  };
  type Envelope = {
    request_id: string; operation: string;
    payload: {session_id?: string; event_id?: string; event?: WireEvent};
  };
  const inputWire: Array<{sessionId: string; eventId: string; event: WireEvent}> = [];
  const openFx = new Set<string>();
  const openPads = new Set<string>();
  const enteredMove = deferred<void>();
  const heldMove = deferred<void>();
  const reports = vi.fn();
  let requestSerial = 0;
  const eventUuid = (serial: number) =>
    `60000000-0000-4000-8000-${String(serial).padStart(12, "0")}`;
  const sdk = createRuntimeSession({
    document: {}, window: {}, navigator: {},
    crypto: {randomUUID: () => eventUuid(++requestSerial)},
    manifestSource: {}, inputOwnership: "host",
    // Explicit synthetic identity reused from runtime_session.test.mjs's
    // fixture, not a claim about the current Product or a shipped manifest.
    assemblyIdentity: {
      distributionContract: "lmdj.web-runtime-host.distribution.v1",
      hostId: "web-runtime-host", hostVersion: "1.2.15",
      platformVersion: "0.3.6", productBuild: "9.8.7.6", protocolVersion: 1,
    },
    seams: {transport: {
      async send(envelope: Envelope) {
        const reply = (result: Record<string, unknown>) => ({
          protocol_version: 1, request_id: envelope.request_id, ok: true, result,
        });
        if (envelope.operation === "performance.record.event") {
          const {session_id, event_id, event} = envelope.payload;
          if (typeof session_id !== "string" || typeof event_id !== "string" || !event) {
            throw new Error("Test transport received an incomplete raw event");
          }
          inputWire.push({sessionId: session_id, eventId: event_id, event: {...event}});
          if (event.kind === "fx_move" && event.value === 630) {
            enteredMove.resolve();
            await heldMove.promise;
          }
          // These counts model only requests that reached this transport;
          // the wire order below is the proof, not a manufactured Core ACK.
          if (event.kind === "fx_engage") openFx.add(event.gesture_id!);
          if (event.kind === "fx_release") openFx.delete(event.gesture_id!);
          if (event.kind === "pad_press") openPads.add(event.gesture_id!);
          if (event.kind === "pad_release") openPads.delete(event.gesture_id!);
          return reply({event_id, accepted_tick: 0, input_sequence: inputWire.length,
            coalesced: false, replayed: false, project_revision: null});
        }
        if (envelope.operation === "performance.record.status") {
          return reply({state: "active", session_id: ids.session,
            performance_id: ids.performance, journal_revision: 1,
            next_flush_seq: 1, pending_event_count: 0,
            open_pad_gestures: openPads.size, open_fx_gestures: openFx.size,
            hold: false, pending_launch: null, last_launch_ack: null,
            project_revision: null});
        }
        throw new Error(`Unexpected test transport operation: ${envelope.operation}`);
      },
    }},
  });
  let idIndex = 0;
  const fixture = controllerFixture({reportFailure: reports,
    createId: () => [ids.session, ids.performance][idIndex++] ?? eventUuid(100 + idIndex)});
  fixture.runtime.session.recordPerformanceEvent = sdk.recordPerformanceEvent;
  fixture.runtime.session.preparePerformancePadEvent = sdk.preparePerformancePadEvent!;
  fixture.runtime.session.queryPerformanceRecordingStatus = sdk.queryPerformanceRecordingStatus;
  const disconnect = fixture.controller.connect();
  const physicalKey = {};
  let lease: ReturnType<typeof sdk.reserveInputGesture> = null;
  try {
    await fixture.controller.refreshRecovery();
    await fixture.controller.record();
    expect(fixture.controller.getState().recording.phase).toBe("recording");
    const fxGesture = fixture.controller.engageFx("filter", 500);
    await waitFor(() => expect(fixture.controller.getState().authority?.openFxGestures).toBe(1));
    expect(reports).not.toHaveBeenCalled();

    fixture.controller.moveFx(fxGesture, "filter", 630);
    await enteredMove.promise;
    lease = sdk.reserveInputGesture(physicalKey, 0, "pointer");
    expect(lease).not.toBeNull();
    const padGesture = eventUuid(900);
    const padPress = fixture.controller.recordRawEvent({
      kind: "pad_press", gestureId: padGesture, slot: 0, velocity: 100,
    }, physicalKey);
    // This integration case has no Pattern consumer. Cancel ONLY its unused
    // preparation; the real SDK Performance claim remains until release.
    lease!.cancelUnsubmittedPattern();
    const padRelease = fixture.controller.recordRawEvent({
      kind: "pad_release", gestureId: padGesture, slot: 0,
    }, physicalKey);
    const padsSettled = Promise.allSettled([padPress, padRelease]);
    fixture.controller.moveFx(fxGesture, "filter", 631);
    fixture.controller.releaseFx(fxGesture, "filter");
    // No fake clock, delayed extra up, enlarged queue or per-event await is
    // inserted in the above reproducing sequence.
    heldMove.resolve();
    const padResults = await padsSettled;
    // Existing Stop awaits rawEventTail. Its modeled lifecycle receipt does
    // not add any FX release to inputWire, so it cannot repair the RED.
    await fixture.controller.stop();
    const failures = reports.mock.calls.map(([, error]) => ({
      code: (error as {code?: string}).code,
      message: (error as Error).message,
    }));
    expect(inputWire.map(({event}) => event),
      `Actual SDK/controller failures: ${JSON.stringify(failures)}`).toEqual([
      {kind: "fx_engage", gesture_id: fxGesture, fx: "filter", value: 500},
      {kind: "fx_move", gesture_id: fxGesture, fx: "filter", value: 630},
      {kind: "pad_press", gesture_id: padGesture, slot: 0, velocity: 100},
      {kind: "pad_release", gesture_id: padGesture, slot: 0},
      {kind: "fx_move", gesture_id: fxGesture, fx: "filter", value: 631},
      {kind: "fx_release", gesture_id: fxGesture, fx: "filter"},
    ]);
    expect(padResults).toEqual([
      {status: "fulfilled", value: undefined}, {status: "fulfilled", value: undefined},
    ]);
    expect(failures).toEqual([]);
    expect(inputWire.every(({sessionId}) => sessionId === ids.session)).toBe(true);
    expect(new Set(inputWire.map(({eventId}) => eventId)).size).toBe(6);
    expect(await sdk.queryPerformanceRecordingStatus()).toMatchObject({
      openPadGestures: 0, openFxGestures: 0,
    });
  } finally {
    heldMove.resolve();
    lease?.cancelUnsubmittedPattern();
    lease?.releasePhysical();
    await fixture.controller.stop();
    disconnect();
  }
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
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
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
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
  await userEvent.click(screen.getByRole("button", {name: "MORE"}));
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

test("headered capture start failure with stopped ACK compensates the already committed begin", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  calls.capture.mockImplementationOnce(async (sink: {onStopped(): void}) => {
    sink.onStopped();
    throw new Error("capture start refused after stopped ACK");
  });
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
    .toContain("Unavailable");
  expect(screen.getByRole("status", {name: "Filter status"}).getAttribute("data-provenance")).toBe("unavailable");
  expect(screen.getByRole("slider", {name: "Cutoff"})
    .hasAttribute("disabled")).toBe(true);
  expect(screen.getByRole("button", {name: "HP"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.queryByText("20.0 kHz")).toBeNull();
  expect(screen.getByRole("button", {name: "LP"}).getAttribute("aria-pressed")).toBe("false");
  // Legacy gestures still take the legacy route after returning to PRIMARY.
  await userEvent.click(screen.getByRole("button", {name: "PRIMARY"}));
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

test("headered capture start without stopped ACK retains the original owner and bytes", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  const original = new Error("headered capture outcome unknown");
  calls.capture.mockRejectedValueOnce(original);
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  expect(calls.stop).toHaveBeenCalledWith({sessionId: ids.session,
    requestId: expect.any(String)});
  expect(fixture.store.discard).not.toHaveBeenCalled();
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording).toMatchObject({
    phase: "stopped", sessionId: ids.session, performanceId: ids.performance,
    expectedRevision: 8,
  });
  expect(fixture.controller.getState().wavStatus).toContain("temporary retained");
  await fixture.controller.save();
  expect(fixture.runtime.session.savePerformance).not.toHaveBeenCalled();
  expect(fixture.store.bind).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording).toMatchObject({
    phase: "stopped", sessionId: ids.session, performanceId: ids.performance,
    expectedRevision: 8,
  });
  expect(fixture.controller.getState().wavStatus).toContain("temporary retained");
  await fixture.controller.discard();
  expect(fixture.runtime.session.savePerformance).not.toHaveBeenCalled();
  expect(fixture.store.bind).not.toHaveBeenCalled();
  expect(fixture.controller.getState().recording).toMatchObject({
    phase: "stopped", sessionId: ids.session, performanceId: ids.performance,
    expectedRevision: 8,
  });
  expect(fixture.controller.getState().wavStatus).toContain("temporary retained");
  expect(fixture.store.save).not.toHaveBeenCalled();
  expect(fixture.store.discard).not.toHaveBeenCalled();
  expect(fixture.cleanupTemporary).not.toHaveBeenCalled();
  await expect(fixture.controller.close()).rejects.toBe(original);
});

test("headered Filter and prepared physical Pad events keep one submission order", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const engage = deferred<void>();
  calls.raw.mockImplementation(async ({eventId, event}) => {
    if (event.kind === "filter_parameter" && event.phase === "engage") {
      await engage.promise;
    }
    return {eventId, gestureGeneration: "ordered-filter-generation",
      recordingGestureId: "ordered-recording-filter", replayed: false};
  });
  const token = fixture.controller.touchFilterEngage("cutoff");
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
  const physicalKey = {};
  const press = fixture.controller.recordRawEvent({kind: "pad_press",
    gestureId: "ordered-pad", slot: 0, velocity: 100}, physicalKey);
  const release = fixture.controller.recordRawEvent({kind: "pad_release",
    gestureId: "ordered-pad", slot: 0}, physicalKey);
  fixture.controller.touchFilterRelease(token, "cutoff");
  expect(calls.prepare.mock.calls.map(([request, key]) => [request.event.kind, key]))
    .toEqual([["pad_press", physicalKey], ["pad_release", physicalKey]]);
  expect(calls.raw).toHaveBeenCalledTimes(1);
  expect(calls.prepare.mock.calls[0]?.[1]).toBe(physicalKey);
  expect(calls.prepare.mock.calls[1]?.[1]).toBe(physicalKey);
  const preparedIds = calls.prepare.mock.calls.map(([request]) => request.eventId);
  engage.resolve();
  await Promise.all([press, release]);
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(4));
  expect(calls.raw.mock.calls.map(([request]) => request.event.kind)).toEqual([
    "filter_parameter", "pad_press", "pad_release", "filter_release",
  ]);
  expect(calls.raw.mock.calls.slice(1, 3).map(([request, key]) => [request.eventId, key]))
    .toEqual(preparedIds.map(eventId => [eventId, physicalKey]));
  expect(calls.raw.mock.calls[1]?.[1]).toBe(physicalKey);
  expect(calls.raw.mock.calls[2]?.[1]).toBe(physicalKey);
  expect(calls.raw.mock.calls[3]?.[0].event).toEqual({kind: "filter_release",
    gestureId: "ordered-recording-filter", gestureGeneration: "ordered-filter-generation"});
  await fixture.controller.stop();
  expect(calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.controller.getState().recording.phase).toBe("stopped");
});

test("a rejected headered control remains the original shutdown debt after capture drains", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const original = Object.assign(new Error("headered control outcome unknown"), {
    code: "HOST_TIMEOUT", details: {pending: true},
  });
  calls.raw.mockRejectedValueOnce(original);
  fixture.controller.turnFilterCutoff(-1);
  await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
  await fixture.controller.stop();
  expect(calls.stop).toHaveBeenCalledTimes(1);
  expect(fixture.captureStop).toHaveBeenCalledTimes(1);
  expect(fixture.order).toContain("tail-drained");
  await expect(fixture.controller.close()).rejects.toBe(original);
});


test("a control queued during Stop does not assign its sessionless failure to the old recording", async () => {
  const reportFailure = vi.fn();
  const fixture = controllerFixture({reportFailure});
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const stopGate = deferred<void>();
  const stop = calls.stop.getMockImplementation()!;
  calls.stop.mockImplementationOnce(async request => {
    await stopGate.promise;
    return stop(request);
  });
  const stopped = fixture.controller.stop();
  await waitFor(() => expect(calls.stop).toHaveBeenCalledTimes(1));
  const original = new Error("sessionless control rejected");
  calls.liveControl.mockRejectedValueOnce(original);
  fixture.controller.turnFilterCutoff(-1);
  expect(calls.liveControl).not.toHaveBeenCalled();
  stopGate.resolve();
  await stopped;
  await waitFor(() => expect(reportFailure).toHaveBeenCalledWith("Perform", original));
  expect(calls.raw).not.toHaveBeenCalled();
  expect(calls.liveControl).toHaveBeenCalledTimes(1);
  await expect(fixture.controller.close()).resolves.toBeUndefined();
});

test("ordinary raw refusal preserves both admitted controls before a prepared physical Pad", async () => {
  const eventIds = ["held-hold-on", "held-hold-off", "refused-hold-on",
    "reserved-pad-press", "reserved-pad-release"];
  const allIds = [ids.session, ids.performance, ...eventIds];
  let identityIndex = 0;
  const fixture = controllerFixture({createId: () =>
    allIds[identityIndex++] ?? `later-${identityIndex}`});
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  calls.begin.mockImplementation(headeredBegin());
  const disconnect = fixture.controller.connect();
  await fixture.controller.refreshRecovery();
  await fixture.controller.refreshLiveStatus();
  await fixture.controller.record();
  const firstGate = deferred<void>();
  const secondGate = deferred<void>();
  const completed: string[] = [];
  const submitted: string[] = [];
  const raw = calls.raw.getMockImplementation()!;
  calls.raw.mockImplementation(async (request, key) => {
    if (request.eventId === eventIds[0]) await firstGate.promise;
    if (request.eventId === eventIds[1]) await secondGate.promise;
    const receipt = await raw(request, key);
    completed.push(request.eventId);
    return receipt;
  });
  const prepare = calls.prepare.getMockImplementation()!;
  calls.prepare.mockImplementation((request, key) => {
    const descriptor = prepare(request, key);
    return {...descriptor, submit() {
      submitted.push(request.eventId);
      return descriptor.submit();
    }};
  });
  const admitted: Promise<void>[] = [];
  try {
    const first = fixture.controller.recordRawEvent({kind: "hold_on"});
    const second = fixture.controller.recordRawEvent({kind: "hold_off"});
    admitted.push(first, second);
    await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(1));
    await expect(fixture.controller.recordRawEvent({kind: "hold_on"}))
      .rejects.toMatchObject({code: "HOST_STATE_INVALID",
        message: "Live input window is full; wait for the current input to settle"});
    const physicalKey = {};
    const press = fixture.controller.recordRawEvent({kind: "pad_press",
      gestureId: "reserved-physical-pad", slot: 0, velocity: 100}, physicalKey);
    const release = fixture.controller.recordRawEvent({kind: "pad_release",
      gestureId: "reserved-physical-pad", slot: 0}, physicalKey);
    admitted.push(press, release);
    expect(calls.prepare).toHaveBeenCalledTimes(2);
    expect(calls.prepare.mock.calls.map(([request]) => request.eventId))
      .toEqual(eventIds.slice(3));
    expect(calls.prepare.mock.calls[0]?.[1]).toBe(physicalKey);
    expect(calls.prepare.mock.calls[1]?.[1]).toBe(physicalKey);
    // One event-loop turn drains all runnable Promise reactions. Both
    // original requests remain explicitly gated; no duration grants passage.
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(calls.raw.mock.calls.map(([request]) => request.eventId))
      .toEqual([eventIds[0]]);
    expect(submitted).toEqual([]);
    expect(completed).toEqual([]);
    firstGate.resolve();
    await first;
    await waitFor(() => expect(calls.raw).toHaveBeenCalledTimes(2));
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(calls.raw.mock.calls.map(([request]) => request.eventId))
      .toEqual(eventIds.slice(0, 2));
    expect(completed).toEqual([eventIds[0]]);
    expect(submitted).toEqual([]);
    secondGate.resolve();
    await Promise.all(admitted);
    expect(calls.raw.mock.calls.map(([request]) => [request.eventId, request.event.kind]))
      .toEqual([[eventIds[0], "hold_on"], [eventIds[1], "hold_off"],
        [eventIds[3], "pad_press"], [eventIds[4], "pad_release"]]);
    expect(completed).toEqual([eventIds[0], eventIds[1], eventIds[3], eventIds[4]]);
    expect(submitted).toEqual(eventIds.slice(3));
    expect(calls.raw.mock.calls[2]?.[1]).toBe(physicalKey);
    expect(calls.raw.mock.calls[3]?.[1]).toBe(physicalKey);
    await fixture.controller.stop();
    expect(calls.stop).toHaveBeenCalledTimes(1);
    expect(fixture.captureStop).toHaveBeenCalledTimes(1);
    expect(fixture.order).toContain("tail-drained");
    expect(fixture.controller.getState().recording.phase).toBe("stopped");
  } finally {
    firstGate.resolve();
    secondGate.resolve();
    await Promise.allSettled(admitted);
    await fixture.controller.stop();
    disconnect();
  }
});

// C2: the masks below are producer readbacks, never a Host-authored Project.
test("current Pad controls expose independent multi-Solo and Mute priority across all 64 slots", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  const view = render(<PerformSurface controller={fixture.controller} project={project}
    bank={0} currentPad={0} />);
  fireEvent.click(screen.getByRole("button", {name: "Live Mute / Solo"}));
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
  fireEvent.click(screen.getByRole("button", {name: "Live Mute / Solo"}));
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


test("exclusive groups share one MASTER and HOLD without producer calls", async () => {
  const fixture = controllerFixture();
  const onChange = vi.fn();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    monitorVolume={{value: 73, disabled: false, onChange}} />);
  for (const [group, sliders] of [
    ["FILTER", ["Cutoff", "Resonance", "MASTER"]],
    ["MORE", ["Stutter", "Gate", "Reverse", "Crush", "Cutter", "MASTER"]],
    ["PRIMARY", ["Filter", "Delay", "Reverb", "MASTER"]],
  ] as const) {
    fireEvent.click(screen.getByRole("button", {name: group}));
    expect(screen.getAllByRole("slider").map(node => node.getAttribute("aria-label"))).toEqual(sliders);
    expect(screen.getAllByRole("button", {name: "HOLD"})).toHaveLength(1);
    expect(screen.getByRole("slider", {name: "MASTER"})).toHaveProperty("value", "73");
  }
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
  expect(onChange).not.toHaveBeenCalled();
});

test.each([
  ["PRIMARY", ["Filter", "Delay", "Reverb"]],
  ["FILTER", ["Type", "Cutoff", "Resonance"]],
  ["MORE", ["Crush", "Stutter", "Gate"]],
] as const)("Live Mute/Solo preserves %s encoder bindings until explicit Back to Filter", (group, labels) => {
  const fixture = controllerFixture();
  let current: ContextualEncoders | null = null;
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    currentPad={0} onEncodersReady={value => { current = value; }} />);
  fireEvent.click(screen.getByRole("button", {name: group}));
  fireEvent.click(screen.getByRole("button", {name: "Live Mute / Solo"}));
  expect(screen.getByRole("region", {name: "Current Pad live controls"})).toBeTruthy();
  expect(Object.values(current!.bindings).map(binding => binding.label)).toEqual(labels);
  fireEvent.click(screen.getByRole("button", {name: "Back to Filter"}));
  expect(screen.getByRole("button", {name: "FILTER"}).getAttribute("aria-pressed")).toBe("true");
  expect(Object.values(current!.bindings).map(binding => binding.label))
    .toEqual(["Type", "Cutoff", "Resonance"]);
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
});

test("switching groups closes removed Primary touch while retaining rotary ownership", async () => {
  const {fixture} = renderSurface();
  act(() => fixture.controller.turnFx("reverb", 2));
  const delay = screen.getByRole("slider", {name: "Delay"});
  fireEvent.pointerDown(delay, {pointerId: 91});
  fireEvent.change(delay, {target: {value: "700"}});
  fireEvent.click(screen.getByRole("button", {name: "FILTER"}));
  await waitFor(() => expect(fixture.runtime.calls.fx.mock.calls
    .filter(([event]) => event.fx === "delay").map(([event]) => event.kind))
    .toEqual(["fx_engage", "fx_move", "fx_release"]));
  expect(fixture.runtime.calls.fx.mock.calls.filter(([event]) => event.fx === "reverb")
    .map(([event]) => event.kind)).toEqual(["fx_engage"]);
  expect(fixture.controller.getState().fx.reverb).toBe(520);
  expect(screen.getByRole("button", {name: "Live"})).toHaveProperty("disabled", false);
});

test("replacing main Cutoff with FILTER closes the old touch before admitting the new input", async () => {
  const fixture = controllerFixture();
  enableTypedCore(fixture.runtime.calls);
  renderSurface(fixture);
  await waitFor(() => expect(fixture.controller.getState().filter.provenance).toBe("core"));
  const old = screen.getByRole("slider", {name: "Filter"});
  fireEvent.pointerDown(old, {pointerId: 92});
  fireEvent.change(old, {target: {value: "700"}});
  await waitFor(() => expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(2));
  fireEvent.click(screen.getByRole("button", {name: "FILTER"}));
  await waitFor(() => expect(fixture.runtime.calls.liveControl.mock.calls.at(-1)?.[0].intent.kind)
    .toBe("filter_release"));
  const replacement = screen.getByRole("slider", {name: "Cutoff"});
  expect(replacement).not.toBe(old);
  fireEvent.pointerDown(replacement, {pointerId: 93});
  await waitFor(() => expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(4));
  fireEvent.lostPointerCapture(old, {pointerId: 92});
  expect(fixture.runtime.calls.liveControl).toHaveBeenCalledTimes(4);
  fireEvent.pointerUp(replacement, {pointerId: 93});
  await waitFor(() => expect(fixture.runtime.calls.liveControl.mock.calls
    .map(([request]) => request.intent.kind))
    .toEqual(["filter_parameter", "filter_parameter", "filter_release", "filter_parameter", "filter_release"]));
});

test("physical group navigation is bounded UI state and unregisters on leave", async () => {
  const fixture = controllerFixture();
  const bind = vi.fn();
  let current: ContextualNavigation | null = null;
  const ready = (value: ContextualNavigation | null) => {current = value; bind(value);};
  const view = render(<PerformSurface controller={fixture.controller} project={project}
    bank={0} onNavigationReady={ready} />);
  expect(current!.directionStep!.backAvailable).toBe(false);
  act(() => current!.directionStep!.onForward());
  expect(screen.getByRole("button", {name: "FILTER"}).getAttribute("aria-pressed")).toBe("true");
  act(() => current!.directionStep!.onForward());
  expect(screen.getByRole("button", {name: "MORE"}).getAttribute("aria-pressed")).toBe("true");
  expect(current!.directionStep!.forwardAvailable).toBe(false);
  act(() => current!.directionStep!.onForward());
  expect(current!.directionStep!.forwardAvailable).toBe(false);
  act(() => current!.directionStep!.onBack());
  act(() => current!.directionStep!.onBack());
  expect(current!.directionStep!.backAvailable).toBe(false);
  expect(fixture.runtime.calls.fx).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.liveControl).not.toHaveBeenCalled();
  view.unmount();
  expect(bind).toHaveBeenLastCalledWith(null);
});


test("touch retirement calls its admitting owner when the controller is replaced", () => {
  const firstRelease = vi.fn();
  const nextRelease = vi.fn();
  const props: Parameters<typeof FxSliderBank>[0] = {
    order: ["filter", "delay", "reverb"], values: {filter: 500, delay: 500, reverb: 500,
      stutter: 500, gate: 500, reverse: 500, crush: 500, cutter: 500},
    filter: {type: "lp", cutoffHz: 20000, resonanceMilli: 0,
      engaged: false, frozen: false, provenance: "unavailable"},
    group: "main", legacyFilterGesture: false, onGroupChange: vi.fn(),
    onEngage: () => "old-token", onMove: vi.fn(), onRelease: firstRelease,
    onFilterType: vi.fn(), onFilterTouchEngage: () => "filter-token",
    onFilterTouchMove: vi.fn(), onFilterTouchRelease: vi.fn(), gestureOwner: {},
  };
  const pointer = (node: HTMLElement, type: string, pointerId: number) => {
    const event = new Event(type, {bubbles: true});
    Object.defineProperty(event, "pointerId", {value: pointerId});
    fireEvent(node, event);
  };
  const view = render(<FxSliderBank {...props} />);
  pointer(screen.getByRole("slider", {name: "Delay"}), "pointerdown", 96);
  view.rerender(<FxSliderBank {...props} gestureOwner={{}} onRelease={nextRelease}
    onEngage={() => "new-token"} />);
  expect(firstRelease).toHaveBeenCalledExactlyOnceWith("old-token", "delay");
  expect(nextRelease).not.toHaveBeenCalled();
  const replacement = screen.getByRole("slider", {name: "Delay"});
  pointer(replacement, "pointerdown", 97);
  pointer(replacement, "lostpointercapture", 96);
  expect(nextRelease).not.toHaveBeenCalled();
  pointer(replacement, "pointerup", 97);
  expect(nextRelease).toHaveBeenCalledExactlyOnceWith("new-token", "delay");
});

test("all-64 mask summary distinguishes a pending mask from an applied empty list", async () => {
  const fixture = controllerFixture();
  const {calls} = fixture.runtime;
  enableTypedCore(calls);
  render(<PerformSurface controller={fixture.controller} project={project} bank={3} currentPad={63} />);
  fireEvent.click(screen.getByRole("button", {name: "Live Mute / Solo"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Solo D16"})).toHaveProperty("disabled", false));
  fireEvent.click(screen.getByRole("button", {name: "Solo D16"}));
  const summary = () => document.querySelector(".perform-pad-gate-summary")!;
  await waitFor(() => expect(summary().textContent).toContain("D16"));
  const read = calls.liveStatus.getMockImplementation()!;
  const applied = deferred<unknown>();
  calls.liveStatus.mockImplementationOnce(() => applied.promise);
  fireEvent.click(screen.getByRole("button", {name: "Mute D16"}));
  await waitFor(() => expect(summary().getAttribute("data-provenance")).toBe("pending"));
  expect([...summary().querySelectorAll("dd")].map(node => node.textContent)).toEqual(["Pending", "Pending"]);
  applied.resolve(await read());
  await waitFor(() => expect([...summary().querySelectorAll("dd")].map(node => node.textContent))
    .toEqual(["D16", "D16"]));
  expect(summary().getAttribute("data-provenance")).toBe("core");
});


test("Slots draft selectors and Escape/back neither launch nor change committed mapping", async () => {
  const fixture = controllerFixture();
  const select = vi.fn();
  render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    onSelectPattern={select} />);
  selectPerformPage("Slots");
  expect((screen.getByRole("option", {name: "Pattern 01"}) as HTMLOptionElement).value).toBe(ids.pattern1);
  expect((screen.getByRole("option", {name: "Pattern 02"}) as HTMLOptionElement).value).toBe(ids.pattern2);
  for (const [name, value] of [["Pattern assignment", ids.pattern2], ["Pattern slot", "15"],
    ["Move Pattern from", "1"], ["Move Pattern to", "14"], ["Clear Pattern slot", "13"]] as const) {
    fireEvent.change(screen.getByRole("combobox", {name}), {target: {value}});
    await userEvent.keyboard("{Escape}");
  }
  expect(screen.getByRole("status", {name: "Selected Pattern slot"}).textContent).toBe("Slot 16 · Empty");
  selectPerformPage("Live");
  expect(screen.getByRole("button", {name: "Launch Pattern 1"}).getAttribute("data-pattern-id")).toBe(ids.pattern1);
  selectPerformPage("Slots");
  expect((screen.getByRole("combobox", {name: "Pattern slot"}) as HTMLSelectElement).value).toBe("15");
  expect(fixture.runtime.session.assignPatternSlot).not.toHaveBeenCalled();
  expect(fixture.runtime.session.clearPatternSlot).not.toHaveBeenCalled();
  expect(fixture.runtime.session.movePatternSlot).not.toHaveBeenCalled();
  expect(fixture.runtime.calls.launch).not.toHaveBeenCalled();
  expect(select).not.toHaveBeenCalled();
  expect(fixture.refreshProject).not.toHaveBeenCalled();
});

test("Slots target readback changes only with refreshed Project Truth, including rejected Assign", async () => {
  const fixture = controllerFixture();
  const rendered = render(<PerformSurface controller={fixture.controller} project={project} bank={0} />);
  selectPerformPage("Slots");
  fireEvent.change(screen.getByRole("combobox", {name: "Pattern slot"}), {target: {value: "2"}});
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Pattern assignment"}), ids.pattern2);
  (fixture.runtime.session.assignPatternSlot as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("revision conflict"));
  await userEvent.click(screen.getByRole("button", {name: "Assign Pattern"}));
  await waitFor(() => expect(fixture.controller.getState().error).toBe("Something went wrong in Creator. Try again. Details are in Developer diagnostics."));
  expect(screen.getByRole("status", {name: "Selected Pattern slot"}).textContent).toBe("Slot 03 · Empty");
  expect(fixture.refreshProject).not.toHaveBeenCalled();
  rendered.rerender(<PerformSurface controller={fixture.controller} bank={0}
    project={{...project, revision: 8, patternSlots: project.patternSlots.map((id, index) => index === 2 ? ids.pattern2 : id)}} />);
  expect(screen.getByRole("status", {name: "Selected Pattern slot"}).textContent).toBe("Slot 03 · Pattern 02");
});

test("Slots structural lock disables all draft controls and actions without disabling ordinary Launch", async () => {
  const fixture = controllerFixture();
  const select = vi.fn();
  const rendered = render(<PerformSurface controller={fixture.controller} project={project} bank={0}
    slotEditingLocked transport={idlePatternTransport()} onSelectPattern={select} />);
  selectPerformPage("Slots");
  const editor = screen.getByRole("group", {name: "Pattern slot editing"});
  for (const control of [...within(editor).getAllByRole("combobox"), ...within(editor).getAllByRole("button")]) {
    expect(control.hasAttribute("disabled")).toBe(true);
  }
  selectPerformPage("Live");
  await userEvent.click(screen.getByRole("button", {name: "Launch Pattern 1"}));
  expect(select).toHaveBeenCalledExactlyOnceWith(ids.pattern1);
  rendered.rerender(<PerformSurface controller={fixture.controller} project={project} bank={0}
    slotEditingLocked={false} transport={idlePatternTransport()} onSelectPattern={select} />);
  selectPerformPage("Slots");
  for (const control of screen.getAllByRole("combobox")) expect(control.hasAttribute("disabled")).toBe(false);
  expect(screen.getByRole("button", {name: "Assign Pattern"}).hasAttribute("disabled")).toBe(false);
});


async function audioReadoutFixture(sampleRate = 48_000) {
  const fixture = await shutdownRecordingFixture();
  let generation = 0;
  let value: import("@lmdj/web-runtime-platform/runtime_types").PerformanceMasterCaptureProgress =
    Object.freeze({state:"unavailable",reason:"idle"});
  const originalStart = fixture.runtime.session.startPerformanceMasterCapture;
  fixture.runtime.session.performanceMasterCaptureProgress = vi.fn(() => value);
  fixture.runtime.session.startPerformanceMasterCapture = async (sink,binding=null) => {
    generation++;
    value=Object.freeze({state:"available",captureId:`60000000-0000-4000-8000-${String(generation).padStart(12,"0")}`,
      generation,binding,sampleRate,receivedFrames:0,phase:"recording",droppedFrames:0,failure:null});
    const handle=await originalStart({
      onBatch(channels){if(value.state==="available")value=Object.freeze({...value,receivedFrames:value.receivedFrames+channels[0].length});sink.onBatch(channels);},
      onFailure(reason,dropped){if(value.state==="available")value=Object.freeze({...value,phase:"failed",failure:"protocol-error",droppedFrames:null});sink.onFailure(reason,dropped);},
      onStopped(){if(value.state==="available" && value.phase!=="failed")value=Object.freeze({...value,phase:"stopped"});sink.onStopped();},
    },binding);
    return {stop(){if(value.state==="available" && value.phase!=="failed")value=Object.freeze({...value,phase:"stopping"});return handle.stop();}};
  };
  return {...fixture,
    emit(frames=4800){expect(frames).toBeGreaterThan(0);expect(frames).toBeLessThanOrEqual(4800);fixture.getSink()!.onBatch([new Float32Array(frames),new Float32Array(frames)]);},
    replaceCapture(){if(value.state==="available")value=Object.freeze({...value,captureId:"70000000-0000-4000-8000-000000000001",generation:99,phase:"recording",receivedFrames:777});},
  };
}

test("audio readout separates received PCM from a slow durable checkpoint and final partial", async () => {
  const f=await audioReadoutFixture();render(<PerformSurface controller={f.controller} project={project} bank={0}/>);
  await userEvent.click(screen.getByRole("button",{name:"Record Performance"}));
  act(()=>{f.emit();f.emit();f.emit(127);});
  const captured=screen.getByRole("status",{name:"Captured audio"});
  const wav=screen.getByRole("status",{name:"Local WAV audio"});
  await waitFor(()=>expect(captured.textContent).toBe("00:00.202"));
  expect(captured.getAttribute("data-frames")).toBe("9727");
  expect(wav.textContent).toBe("00:00.000");
  const prior=f.controller.getState().recordingAudio!;
  expect(prior.wav!.snapshot.durableFrames).toBe(0);
  const gate=deferred<void>();f.holdNextCheckpoint(gate.promise);
  let stopping!:Promise<void>;act(()=>{stopping=f.controller.stop();});
  await waitFor(()=>expect(f.checkpointEntered()).toBe(true));
  expect(wav.getAttribute("data-frames")).toBe("0");expect(wav.getAttribute("data-settled")).toBe("false");
  await act(async()=>{gate.resolve();await stopping;});
  expect(wav.textContent).toBe("00:00.202");expect(wav.getAttribute("data-frames")).toBe("9727");
  expect(wav.getAttribute("data-settled")).toBe("true");
  expect(new DataView(f.bytes().buffer).getUint32(40,true)/4).toBe(9727);
  expect(prior.wav!.snapshot.durableFrames).toBe(0);
  expect(Object.isFrozen(f.controller.getState().recordingAudio!.wav!.snapshot)).toBe(true);
  selectPerformPage("Takes");expect(screen.getByRole("status",{name:"Local WAV audio"}).textContent).toBe("00:00.202");
});

test("captured time uses its actual rate while local WAV uses its own header format", async () => {
  const f=await audioReadoutFixture(44_100);render(<PerformSurface controller={f.controller} project={project} bank={0}/>);
  await userEvent.click(screen.getByRole("button",{name:"Record Performance"}));
  act(()=>f.emit(4410));await act(async()=>{await f.controller.stop();});
  expect(screen.getByRole("status",{name:"Captured audio"}).textContent).toBe("00:00.100");
  expect(screen.getByRole("status",{name:"Local WAV audio"}).textContent).toBe("00:00.091");
  expect(new DataView(f.bytes().buffer).getUint32(24,true)).toBe(48_000);
});

test("a retained WAV prefix shows known storage drops and keeps unknown tap loss distinct", async () => {
  const f=await audioReadoutFixture();render(<PerformSurface controller={f.controller} project={project} bank={0}/>);
  await userEvent.click(screen.getByRole("button",{name:"Record Performance"}));
  act(()=>{for(let i=0;i<32;i++)f.emit();});
  await waitFor(()=>expect(f.writer.snapshot.durableFrames).toBe(153600));
  act(()=>f.emit(1000));
  await waitFor(()=>expect(f.writer.attemptedFrames).toBe(154600));
  act(()=>f.getSink()!.onFailure("tap-failure",0));
  await waitFor(()=>expect(f.controller.getState().recording.phase).toBe("stopped"));
  expect(screen.getByRole("status",{name:"Local WAV audio"}).getAttribute("data-frames")).toBe("153600");
  expect(screen.getByRole("status",{name:"Local WAV audio"}).getAttribute("data-dropped-frames")).toBe("1000");
  expect(screen.getByText("Local WAV prefix")).toBeTruthy();
  expect(screen.getByText("Additional audio loss unknown")).toBeTruthy();
  expect(f.controller.getState().recordingAudio!.tapLoss).toBeNull();
  expect(f.controller.getState().recordingAudio!.capture.state).toBe("available");
});

test("late checkpoint publication never adopts another capture's frames", async () => {
  const f=await audioReadoutFixture();await f.controller.record();f.emit(127);
  const original=f.controller.getState().recordingAudio!;
  const gate=deferred<void>();f.holdNextCheckpoint(gate.promise);
  const stop=f.controller.stop();await waitFor(()=>expect(f.checkpointEntered()).toBe(true));
  expect(f.captureOwned()).toBe(false);f.replaceCapture();gate.resolve();await stop;
  const final=f.controller.getState().recordingAudio!;
  expect(final.capture).toEqual({state:"unavailable",reason:"owner-lost"});
  expect(final.wav!.snapshot.durableFrames).toBe(127);
  expect(original.capture.state==="available" && original.capture.receivedFrames).toBe(127);
});

test("controller close clears visible audio before delayed original writer callbacks settle", async () => {
  const f=await audioReadoutFixture();await f.controller.record();f.emit(127);
  const gate=deferred<void>();f.holdNextCheckpoint(gate.promise);
  const closing=f.controller.close();
  await waitFor(()=>expect(f.checkpointEntered()).toBe(true));
  expect(f.controller.getState().recordingAudio).toBeNull();
  gate.resolve();await closing;
  expect(f.controller.getState().recordingAudio).toBeNull();
  expect(new DataView(f.bytes().buffer).getUint32(40,true)/4).toBe(127);
});

test("audio facts survive Save UNKNOWN and bind retry until confirmed finalization", async () => {
  const f=await audioReadoutFixture();await f.controller.record();f.emit(127);await f.controller.stop();
  const original=f.controller.getState().recordingAudio;
  const save=f.save.getMockImplementation()! as CreatorPerformanceRuntimeSession["savePerformance"];
  f.save.mockImplementationOnce(async(request)=>{await save(request);throw new Error("save outcome unknown");});
  f.inspect.mockRejectedValueOnce(new Error("readback unavailable"));
  await f.controller.save("Audio Facts");
  expect(f.controller.getState().recording.phase).toBe("stopped");expect(f.controller.getState().recordingAudio).toBe(original);
  f.bind.mockRejectedValueOnce(new Error("bind unavailable"));
  await f.controller.save("Audio Facts");
  expect(f.controller.getState().bindingStatus).toBe("retry");expect(f.controller.getState().recordingAudio).toBe(original);
  await f.controller.retryWavBind();
  expect(f.controller.getState().bindingStatus).toBe("bound");expect(f.controller.getState().recordingAudio).toBeNull();
  expect(f.save).toHaveBeenCalledTimes(1);
});


test.each([
  [0, "Local WAV"],
  [1, "Local WAV prefix"],
] as const)("frame-limit readout with %i dropped frames uses %s", (droppedFrames, label) => {
  render(<RecordingAudioReadout progress={{
    sessionId: ids.session,
    performanceId: ids.performance,
    capture: {state: "available", captureId: "60000000-0000-4000-8000-000000000001",
      generation: 1, binding: null, sampleRate: 48_000,
      receivedFrames: 86_400_000 + droppedFrames, phase: "stopped",
      droppedFrames: 0, failure: null},
    tapLoss: 0,
    wav: {format: {sampleRate: 48_000, channels: 2}, settled: true,
      snapshot: {state: "sealed", durableFrames: 86_400_000, byteLength: 345_600_044,
        reason: "frame-limit", droppedFrames}},
  }} />);
  expect(screen.getByText(label, {selector: "dt", exact: true})).toBeTruthy();
});

const SAVED_TAKE = Object.freeze({performanceId: ids.performance, name: "Silent Take",
  createdBpm: 120, eventCount: 0, recordingArtifact: Object.freeze({
    sha256: "985ee1bbde8458eeb675cff7bb99b6bd61278b9646a127c7c39b1fb7634cb2d5",
    mediaType: "audio/wav" as const, byteLength: 192124})});

function savedTakeMetadata(performanceId = ids.performance, revision = 7) {
  return {projectId: ids.project, performanceId, projectRevision: revision, recordingRevision: 17,
    recordingArtifact: SAVED_TAKE.recordingArtifact,
    audioMetadata: {sampleRate: 48000 as const, channels: 2 as const, sourceFrames: 48017}, audioError: null};
}

async function savedTakeFixture() {
  const f = controllerFixture();
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([SAVED_TAKE]);
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValue(savedTakeMetadata());
  await f.controller.refreshPerformances();
  return f;
}

test("saved Take selection uses the exact verified selector and never hashes on list refresh", async () => {
  const f = await savedTakeFixture();
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
  await f.controller.inspectTakeAudio(ids.performance);
  expect(f.runtime.session.queryPerformanceRecordingMetadata).toHaveBeenCalledExactlyOnceWith({
    projectId: ids.project, performanceId: ids.performance, expectedRevision: 7,
    recordingArtifact: SAVED_TAKE.recordingArtifact,
  }, {signal: expect.any(AbortSignal)});
  const value = f.controller.getState().takeAudio;
  expect(value?.state).toBe("verified");expect(value?.owner).toBe(project);
  expect(value?.metadata).toEqual(savedTakeMetadata());
  expect(SAVED_TAKE.eventCount).toBe(0);
});

test("Takes renders a real silent WAV time and keeps Replay a separate explicit action", async () => {
  const f = await savedTakeFixture();renderSurface(f);
  await waitFor(() => expect(f.controller.getState().performancesStatus).toBe("ready"));
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
  selectPerformPage("Takes");
  const output = await screen.findByRole("status", {name: "Take WAV audio"});
  await waitFor(() => expect(output.textContent).toBe("00:01.000"));
  expect(output.getAttribute("data-frames")).toBe("48017");
  expect(output.getAttribute("data-rate")).toBe("48000");
  expect(screen.getByText("Recording completeness unknown")).not.toBeNull();
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
  expect(screen.getByRole("button", {name: "Replay selected Take"})).not.toBeNull();
});

test("no-WAV Takes never submit a metadata query or invent a zero duration", async () => {
  const f = await savedTakeFixture();
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([{...SAVED_TAKE, recordingArtifact: null}]);
  await f.controller.refreshPerformances();await f.controller.inspectTakeAudio(ids.performance);
  expect(f.controller.getState().takeAudio?.state).toBe("no-wav");
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
});

test("Saved Takes excludes recovery drafts while a real saved Take remains selectable", async () => {
  const f = await savedTakeFixture(), savedId = ids.pattern2;
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([SAVED_TAKE,
    {...SAVED_TAKE, performanceId: savedId, name: "Earlier saved Take"}]);
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([{
    sessionId: ids.session, performanceId: ids.performance, reason: "owner_lost",
    durableEventCount: 0, pendingEventCount: 0, fingerprint: "f".repeat(64)}]);
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValue(savedTakeMetadata(savedId));
  renderSurface(f);selectPerformPage("Takes");
  await screen.findByRole("button", {name: /^Select Take \d+: Earlier saved Take$/});
  expect(screen.queryByRole("button", {name: /^Select Take \d+: Silent Take$/})).toBeNull();
  await waitFor(() => expect(screen.getByRole("status", {name: "Take WAV audio"}).textContent).toBe("00:01.000"));
  expect(f.runtime.session.queryPerformanceRecordingMetadata).toHaveBeenCalledTimes(1);
  expect(vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mock.calls.every(([request]) =>
    request.performanceId === savedId)).toBe(true);
  await f.controller.inspectTakeAudio(ids.performance);
  expect(f.controller.getState().takeAudio).toBeNull();
});

test("the current unsaved recording is never queried as a saved Take", async () => {
  const f = await savedTakeFixture(), savedId = ids.pattern2;
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([SAVED_TAKE,
    {...SAVED_TAKE, performanceId: savedId, name: "Earlier saved Take"}]);
  await f.controller.refreshRecovery();await f.controller.record();
  expect(f.controller.getState().recording.performanceId).toBe(ids.performance);
  await f.controller.refreshPerformances();await f.controller.inspectTakeAudio(ids.performance);
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValue(savedTakeMetadata(savedId));
  await f.controller.inspectTakeAudio(savedId);
  expect(f.controller.getState().takeAudio?.state).toBe("verified");
  await f.controller.stop();await f.controller.inspectTakeAudio(ids.performance);
  expect(f.controller.getState().takeAudio).toBeNull();
  expect(f.runtime.session.queryPerformanceRecordingMetadata).toHaveBeenCalledTimes(1);
  await f.controller.discard();
});

test("an unavailable recovery snapshot refuses the partial saved list until explicit retry", async () => {
  const f = await savedTakeFixture();
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockRejectedValueOnce(new Error("recovery read unavailable"));
  await expect(f.controller.refreshPerformances()).rejects.toThrow("recovery read unavailable");
  expect(f.controller.getState().performancesStatus).toBe("unavailable");
  expect(f.controller.getState().performances).toEqual([]);
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
  await f.controller.refreshPerformances();await f.controller.inspectTakeAudio(ids.performance);
  expect(f.controller.getState().takeAudio?.state).toBe("verified");
});

test("verified unsupported format and outer integrity or storage refusal remain distinct Take states", async () => {
  const f = await savedTakeFixture();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValueOnce({
    ...savedTakeMetadata(), audioMetadata: null,
    audioError: {code: "UNSUPPORTED_AUDIO", message: "unsupported audio", details: {}}});
  await f.controller.inspectTakeAudio(ids.performance);
  expect(f.controller.getState().takeAudio?.state).toBe("unsupported");
  expect(f.controller.getState().takeAudio?.metadata?.recordingArtifact).toEqual(SAVED_TAKE.recordingArtifact);
  for (const [code, details, state] of [
    ["COOK_FAILED", {storage_condition: "artifact_mismatch"}, "damaged"],
    ["IO_ERROR", {reason: "bounded_read_unavailable"}, "unavailable"],
    ["REVISION_CONFLICT", {}, "unavailable"],
  ] as const) {
    vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockRejectedValueOnce(
      Object.assign(new Error("private platform details"), {code, details}));
    await f.controller.inspectTakeAudio(ids.performance);
    expect(f.controller.getState().takeAudio?.state).toBe(state);
    expect(f.controller.getState().takeAudio?.metadata).toBeNull();
  }
});

test("a failed Take check retries only when explicitly requested", async () => {
  const f = await savedTakeFixture();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockRejectedValueOnce(new Error("offline"));
  renderSurface(f);selectPerformPage("Takes");
  const retry = await screen.findByRole("button", {name: "Retry audio check"});
  await waitFor(() => expect(f.controller.getState().takeAudio?.state).toBe("unavailable"));
  expect(f.runtime.session.queryPerformanceRecordingMetadata).toHaveBeenCalledTimes(1);
  await userEvent.click(retry);
  await waitFor(() => expect(screen.getByRole("status", {name: "Take WAV audio"}).textContent).toBe("00:01.000"));
  expect(f.runtime.session.queryPerformanceRecordingMetadata).toHaveBeenCalledTimes(2);
});

test("a changed selection aborts its observer and cannot adopt a valid late predecessor", async () => {
  const f = await savedTakeFixture(), old = deferred<ReturnType<typeof savedTakeMetadata>>();
  const secondId = "66666666-6666-4666-8666-666666666666";
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([SAVED_TAKE, {...SAVED_TAKE, performanceId: secondId}]);
  await f.controller.refreshPerformances();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockImplementationOnce(() => old.promise)
    .mockResolvedValueOnce(savedTakeMetadata(secondId));
  const pending = f.controller.inspectTakeAudio(ids.performance);
  const firstSignal = vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mock.calls[0]![1]!.signal!;
  await f.controller.inspectTakeAudio(secondId);expect(firstSignal.aborted).toBe(true);
  old.resolve(savedTakeMetadata());await pending;
  expect(f.controller.getState().takeAudio?.performanceId).toBe(secondId);
  expect(f.controller.getState().takeAudio?.state).toBe("verified");
});

test("same-Project owner replacement and revision changes refuse valid late Take receipts", async () => {
  for (const revision of [7, 8]) {
    const f = await savedTakeFixture(), old = deferred<ReturnType<typeof savedTakeMetadata>>();
    vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockImplementationOnce(() => old.promise);
    const pending = f.controller.inspectTakeAudio(ids.performance);
    const nextProject = {...project, revision};
    f.setCreatorState(creatorState({project: {phase: "ready", projects: [], current: nextProject}}));
    old.resolve(savedTakeMetadata());await pending;
    expect(f.controller.getState().takeAudio?.state).not.toBe("verified");
    await f.controller.refreshPerformances();
    vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValueOnce(savedTakeMetadata(ids.performance, revision));
    await f.controller.inspectTakeAudio(ids.performance);
    expect(f.controller.getState().takeAudio?.owner).toBe(nextProject);
    expect(f.controller.getState().takeAudio?.metadata?.projectRevision).toBe(revision);
  }
});

test("list refresh generations and replaced owners never adopt out-of-order saved Takes", async () => {
  const f = await savedTakeFixture(), old = deferred<readonly PerformanceSummary[]>(), next = deferred<readonly PerformanceSummary[]>();
  vi.mocked(f.runtime.session.listPerformances).mockImplementationOnce(() => old.promise).mockImplementationOnce(() => next.promise);
  const a = f.controller.refreshPerformances(), b = f.controller.refreshPerformances();
  next.resolve([{...SAVED_TAKE, name: "Latest Take"}]);await b;
  old.resolve([SAVED_TAKE]);await a;
  expect(f.controller.getState().performances[0]!.name).toBe("Latest Take");
  const stale = deferred<readonly PerformanceSummary[]>();
  vi.mocked(f.runtime.session.listPerformances).mockImplementationOnce(() => stale.promise);
  const pending = f.controller.refreshPerformances();
  const newOwner = {...project};f.setCreatorState(creatorState({project: {phase: "ready", projects: [], current: newOwner}}));
  await f.controller.refreshPerformances();
  stale.reject(new Error("old owner's read failed"));await pending;
  expect(f.controller.getState().performancesOwner).toBe(newOwner);
  expect(f.controller.getState().performancesStatus).toBe("ready");
});

test("Take metadata rejects every mismatched owner revision or complete Artifact receipt", async () => {
  const f = await savedTakeFixture();
  for (const change of [
    {projectId: ids.pattern1}, {performanceId: ids.pattern2}, {projectRevision: 8},
    {recordingArtifact: {...SAVED_TAKE.recordingArtifact, sha256: "f".repeat(64)}},
    {recordingArtifact: {...SAVED_TAKE.recordingArtifact, byteLength: 192125}},
  ]) {
    vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockResolvedValueOnce({...savedTakeMetadata(), ...change});
    await f.controller.inspectTakeAudio(ids.performance);
    expect(f.controller.getState().takeAudio?.state).toBe("unavailable");
    expect(f.controller.getState().takeAudio?.metadata).toBeNull();
  }
});

test("held Take metadata leaves the Project mutation tail available and retires on mutation or close", async () => {
  const f = await savedTakeFixture(), gate = deferred<ReturnType<typeof savedTakeMetadata>>();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockImplementationOnce(() => gate.promise);
  vi.mocked(f.runtime.session.assignPatternSlot).mockResolvedValue({patternSlot: 2, patternId: ids.pattern1,
    committedRevision: 8, replayed: false, projectRevision: 8});
  const pending = f.controller.inspectTakeAudio(ids.performance);
  const signal = vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mock.calls[0]![1]!.signal!;
  let committed = false;const mutation = f.controller.assignPattern(2, ids.pattern1).then(() => {committed = true;});
  try {
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(committed, "far-side Pattern receipt precedes releasing the WAV check").toBe(true);
    expect(signal.aborted).toBe(true);
    expect(f.controller.getState().takeAudio).toBeNull();
  } finally {gate.resolve(savedTakeMetadata());await Promise.all([pending, mutation]);}
  const closing = deferred<ReturnType<typeof savedTakeMetadata>>();
  vi.mocked(f.runtime.session.queryPerformanceRecordingMetadata).mockImplementationOnce(() => closing.promise);
  const late = f.controller.inspectTakeAudio(ids.performance);
  await f.controller.close();closing.resolve(savedTakeMetadata());await late;
  expect(f.controller.getState().takeAudio).toBeNull();
});

const REPLAY_PLAYING = {replayId: "replay-1", state: "playing" as const,
  resolvedRevision: 7, eventCursor: 0, eventCount: 4, projectRevision: null};

async function replaySurfaceFixture(options: NonNullable<Parameters<typeof controllerFixture>[0]> = {}) {
  const fixture = controllerFixture(options);
  vi.mocked(fixture.runtime.session.listPerformances).mockResolvedValue([SAVED_TAKE]);
  const rendered = renderSurface(fixture);
  selectPerformPage("Replay");
  await screen.findByRole("button", {name: `Replay ${SAVED_TAKE.name}`});
  return {fixture, rendered};
}

test("Replay cards expose only saved Takes and never start audio metadata or a publisher on entry", async () => {
  const f = controllerFixture();
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([
    {...SAVED_TAKE, performanceId: ids.pattern2, name: "Saved evening"},
    {...SAVED_TAKE, name: "Unsaved current"},
    {...SAVED_TAKE, performanceId: ids.pattern1, name: "Recovery draft"},
  ]);
  f.controller.connect();await f.controller.refreshRecovery();
  await f.controller.record();await f.controller.stop();
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([{
    sessionId: ids.pattern1, performanceId: ids.pattern1, reason: "owner_lost",
    durableEventCount: 1, pendingEventCount: 0, fingerprint: "f".repeat(64),
  }]);
  await f.controller.refreshPerformances();await f.controller.refreshRecovery();
  renderSurface(f);selectPerformPage("Replay");
  await screen.findByRole("button", {name: "Replay Saved evening"});
  await act(async () => {for (let n = 0; n < 32; n++) await Promise.resolve();});
  expect(screen.queryByRole("button", {name: "Replay Unsaved current"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Replay Recovery draft"})).toBeNull();
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
  expect(screen.getByRole("button", {name: "Apply recovery"})).not.toBeNull();
});

test("a Core-stopped recovered draft stays replayable separately without an in-memory apply flag", async () => {
  const f = controllerFixture();
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([{...SAVED_TAKE,
    name: "Recovered recording", recordingArtifact: null}]);
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([{
    sessionId: ids.session, performanceId: ids.performance, reason: "stopped",
    durableEventCount: 0, pendingEventCount: 0, fingerprint: "f".repeat(64),
  }]);
  vi.mocked(f.runtime.session.queryPerformanceRecordingStatus).mockResolvedValue(authority({
    state: "stopped", journalRevision: project.revision,
  }));
  vi.mocked(f.runtime.session.beginPerformanceReplay).mockResolvedValue(REPLAY_PLAYING);
  renderSurface(f);selectPerformPage("Replay");
  await act(() => f.controller.refreshAuthority());
  const draft = await screen.findByRole("region", {name: "Stopped Performance draft"});
  expect(within(draft).getByText("Not saved yet · save or discard to finish.")).not.toBeNull();
  await userEvent.click(within(draft).getByRole("button", {name: "Replay Recovered recording"}));
  expect(f.runtime.session.beginPerformanceReplay).toHaveBeenCalledWith({
    replayId: expect.any(String), performanceId: ids.performance,
  });
  expect(f.runtime.session.applyPerformanceRecovery).not.toHaveBeenCalled();
  expect(f.runtime.session.queryPerformanceRecordingMetadata).not.toHaveBeenCalled();
});

async function stoppedDraftFixture(statusOverrides: Record<string, unknown> = {}) {
  const f = controllerFixture();
  vi.mocked(f.runtime.session.listPerformances).mockResolvedValue([{...SAVED_TAKE,
    name: "Recovered recording", recordingArtifact: null}]);
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([{
    sessionId: ids.session, performanceId: ids.performance, reason: "stopped",
    durableEventCount: 0, pendingEventCount: 0, fingerprint: "f".repeat(64),
  }]);
  vi.mocked(f.runtime.session.queryPerformanceRecordingStatus).mockResolvedValue(authority({
    state: "stopped", journalRevision: project.revision, ...statusOverrides,
  }));
  await f.controller.refreshPerformances();
  return f;
}

for (const [name, status] of [
  ["active", {state: "active"}], ["unapplied recovery", {state: "recovery_required"}],
  ["pending tail", {pendingEventCount: 1}], ["old revision", {journalRevision: project.revision - 1}],
  ["missing session", {sessionId: null}], ["missing Performance", {performanceId: null}],
] as const) {
  test(`Replay does not admit a stopped draft from ${name} authority`, async () => {
    const f = await stoppedDraftFixture(status);
    expect(f.controller.getState().stoppedDraft).toBeNull();
    await f.controller.saveStoppedDraft();await f.controller.discardStoppedDraft();
    expect(f.runtime.session.savePerformance).not.toHaveBeenCalled();
    expect(f.runtime.session.discardPerformance).not.toHaveBeenCalled();
  });
}

test("stopped draft actions reject a changed Project owner even at the same revision", async () => {
  const f = await stoppedDraftFixture();
  f.setCreatorState({...creatorState(), project: {...creatorState().project, current: {...project}}});
  await f.controller.saveStoppedDraft();await f.controller.discardStoppedDraft();
  expect(f.runtime.session.savePerformance).not.toHaveBeenCalled();
  expect(f.runtime.session.discardPerformance).not.toHaveBeenCalled();
});

test("a failed stopped-authority read publishes no partial saved snapshot", async () => {
  const f = await stoppedDraftFixture();
  vi.mocked(f.runtime.session.queryPerformanceRecordingStatus).mockRejectedValueOnce(new Error("status unavailable"));
  await expect(f.controller.refreshPerformances()).rejects.toThrow("status unavailable");
  expect(f.controller.getState().stoppedDraft).toBeNull();
  expect(f.controller.getState().performancesStatus).toBe("unavailable");
  expect(f.controller.getState().performances).toEqual([]);
});

test("the stopped-authority read remains inside the WAV observation lifetime", async () => {
  const f = controllerFixture();
  f.controller.connect();await f.controller.refreshRecovery();
  await f.controller.record();await f.controller.stop();
  const status = deferred<Awaited<ReturnType<typeof f.runtime.session.queryPerformanceRecordingStatus>>>();
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([{
    sessionId: ids.session, performanceId: ids.performance, reason: "stopped",
    durableEventCount: 0, pendingEventCount: 0, fingerprint: "f".repeat(64),
  }]);
  const statusQuery = vi.mocked(f.runtime.session.queryPerformanceRecordingStatus);
  const saveHeadersObserved = deferred<void>();
  statusQuery.mockClear();statusQuery.mockReturnValueOnce(status.promise)
    .mockImplementationOnce(async () => {
      saveHeadersObserved.resolve();
      return authority({state: "stopped", journalRevision: project.revision});
    });
  const observing = f.controller.refreshPerformances();
  await vi.waitFor(() => expect(statusQuery).toHaveBeenCalledOnce());
  const saving = f.controller.save("Waiting for status observer");
  try {
    await saveHeadersObserved.promise;
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(f.store.bind, "managed bytes cannot be installed while status can still run recovery").not.toHaveBeenCalled();
  } finally {
    status.resolve(authority({state: "stopped", journalRevision: project.revision}));
    await Promise.all([observing, saving]);
  }
  expect(f.store.bind).toHaveBeenCalledOnce();
});

test.each([false, true])("stopped draft completion uses the real lifecycle once (discard=%s)", async discard => {
  const f = await stoppedDraftFixture();
  const operation = discard ? vi.mocked(f.runtime.session.discardPerformance) : vi.mocked(f.runtime.session.savePerformance);
  const receipt = deferred<{performanceId: string; committedRevision: number; replayed: boolean; projectRevision: number}>();
  operation.mockReturnValueOnce(receipt.promise);
  const complete = discard ? () => f.controller.discardStoppedDraft() : () => f.controller.saveStoppedDraft();
  const first = complete(), duplicate = complete();
  await vi.waitFor(() => expect(operation).toHaveBeenCalledOnce());
  expect(f.controller.getState().stoppedDraft).toBeNull();
  const request = {expectedRevision: project.revision, performanceId: ids.performance};
  expect(operation).toHaveBeenCalledWith(discard ? request : {...request, name: "Recovered recording", recordingArtifact: null});
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([]);
  receipt.resolve({performanceId: ids.performance, committedRevision: 10, projectRevision: 10, replayed: false});
  await Promise.all([first, duplicate]);
  expect(f.controller.getState().performancesStatus).toBe("ready");
  expect(f.controller.getState().stoppedDraft).toBeNull();
  expect(f.store.bind).not.toHaveBeenCalled();
  expect(f.store.discard).not.toHaveBeenCalled();
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
});

test("an unconfirmed stopped-draft save cannot claim success or reuse its old selector", async () => {
  const f = await stoppedDraftFixture();
  vi.mocked(f.runtime.session.savePerformance).mockRejectedValueOnce(Object.assign(new Error("reply lost"), {code: "HOST_TIMEOUT"}));
  await f.controller.saveStoppedDraft();await f.controller.saveStoppedDraft();
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(f.controller.getState().saveConfirmation).toBeNull();
  expect(f.controller.getState().stoppedDraft).toBeNull();
  expect(f.controller.getState().performancesStatus).toBe("unavailable");
});

test("leaving waits for an admitted stopped-draft Save without starting another owner", async () => {
  const f = await stoppedDraftFixture();
  const receipt = deferred<{performanceId: string; committedRevision: number; replayed: boolean; projectRevision: number}>();
  vi.mocked(f.runtime.session.savePerformance).mockReturnValueOnce(receipt.promise);
  const saving = f.controller.saveStoppedDraft();
  await vi.waitFor(() => expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce());
  let left = false;
  const leaving = f.controller.leave().then(() => {left = true;});
  try {
    for (let n = 0; n < 32; n++) await Promise.resolve();
    expect(left, "the admitted mutation owns the existing finalization barrier").toBe(false);
  } finally {
    vi.mocked(f.runtime.session.listPerformanceRecovery).mockResolvedValue([]);
    receipt.resolve({performanceId: ids.performance, committedRevision: 10, projectRevision: 10, replayed: false});
    await Promise.all([saving, leaving]);
  }
  expect(left).toBe(true);
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
  expect(f.runtime.calls.capture).not.toHaveBeenCalled();
});

test("a late stopped-status snapshot cannot republish a replaced Project owner", async () => {
  const f = await stoppedDraftFixture();
  const status = deferred<Awaited<ReturnType<typeof f.runtime.session.queryPerformanceRecordingStatus>>>();
  const query = vi.mocked(f.runtime.session.queryPerformanceRecordingStatus);
  query.mockClear();query.mockReturnValueOnce(status.promise);
  const pending = f.controller.refreshPerformances();
  await vi.waitFor(() => expect(query).toHaveBeenCalledOnce());
  const nextProject = {...project};
  f.setCreatorState({...creatorState(), project: {...creatorState().project, current: nextProject}});
  status.resolve(authority({state: "stopped", journalRevision: project.revision}));
  await pending;
  expect(f.controller.getState().stoppedDraft).toBeNull();
  await f.controller.saveStoppedDraft();
  expect(f.runtime.session.savePerformance).not.toHaveBeenCalled();
});

test("an owned Save UNKNOWN has no confirmation until actual inspection resolves it", async () => {
  const f = controllerFixture();
  await f.controller.refreshRecovery();await f.controller.record();await f.controller.stop();
  vi.mocked(f.runtime.session.savePerformance).mockRejectedValueOnce(Object.assign(new Error("lost reply"), {code: "HOST_TIMEOUT"}));
  vi.mocked(f.runtime.session.inspectPerformance).mockRejectedValueOnce(new Error("inspection unavailable"));
  await f.controller.save("Unknown take");
  expect(f.controller.getState().saveConfirmation).toBeNull();
  f.store.bind.mockRejectedValueOnce(new Error("retain pending WAV"));
  vi.mocked(f.runtime.session.inspectPerformance).mockResolvedValueOnce({id: ids.performance,
    name: "Unknown take", createdBpm: 120, recordingArtifact: null, events: [], projectRevision: 10});
  await f.controller.save("Changed field cannot rename unknown take");
  expect(f.controller.getState().saveConfirmation).toEqual({performanceId: ids.performance,
    name: "Unknown take", projectRevision: 10, source: "inspection"});
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
});

test("an inspection of a same-name durable draft is never labelled an acknowledged Save", async () => {
  const f = controllerFixture();
  renderSurface(f);
  await f.controller.refreshRecovery();await act(() => f.controller.record());await act(() => f.controller.stop());
  vi.mocked(f.runtime.session.savePerformance).mockRejectedValueOnce(Object.assign(new Error("unconfirmed save"), {code: "HOST_TIMEOUT"}));
  vi.mocked(f.runtime.session.inspectPerformance).mockResolvedValueOnce({id: ids.performance,
    name: "Untitled Performance", createdBpm: 120, recordingArtifact: null, events: [], projectRevision: 8});
  f.store.bind.mockRejectedValueOnce(new Error("WAV binding not confirmed"));
  await act(() => f.controller.save("Untitled Performance"));selectPerformPage("Takes");
  const observation = await screen.findByRole("status", {name: "Performance save confirmation"});
  expect(observation.textContent).toBe("Performance inspected");
  expect(observation.getAttribute("data-confirmation-source")).toBe("inspection");
  expect(screen.queryByText("Performance saved", {exact: true})).toBeNull();
});

test("an acknowledged Performance Save stays visible while its WAV bind needs retry", async () => {
  const f = controllerFixture();
  f.store.bind.mockRejectedValueOnce(Object.assign(new Error("bind contention"), {code: "PROJECT_BUSY"}));
  renderSurface(f);
  await userEvent.click(screen.getByRole("button", {name: "Record Performance"}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Performance"}));
  await act(() => f.controller.save("Saved events"));
  selectPerformPage("Takes");
  const confirmed = await screen.findByRole("status", {name: "Performance save confirmation"});
  expect(confirmed.textContent).toBe("Performance saved");
  expect(screen.getByRole("status", {name: "WAV binding status"}).textContent).toBe("retry");
  expect(confirmed.getAttribute("data-performance-id")).toBe(ids.performance);
  expect(confirmed.getAttribute("data-project-revision")).toBe("10");
  expect(confirmed.getAttribute("data-confirmation-source")).toBe("save");
  expect(screen.getByRole("textbox", {name: "Performance name"}).hasAttribute("disabled")).toBe(true);
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  const list = vi.mocked(f.runtime.session.listPerformances);list.mockClear();
  await expect(f.controller.refreshPerformances()).rejects.toThrow("Bind or discard");
  expect(list).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Retry WAV bind"}));
  await waitFor(() => expect(f.controller.getState().bindingStatus).toBe("bound"));
  expect(f.runtime.session.savePerformance).toHaveBeenCalledOnce();
  expect(screen.queryByRole("status", {name: "Performance save confirmation"})).toBeNull();
});

test("Replay consumes actual public cursors and keeps reset pending until the terminal Stop acknowledgement", async () => {
  const {fixture: f} = await replaySurfaceFixture();
  const session = f.runtime.session;
  vi.mocked(session.beginPerformanceReplay).mockResolvedValue(REPLAY_PLAYING);
  vi.mocked(session.queryPerformanceReplayStatus).mockResolvedValue({...REPLAY_PLAYING, eventCursor: 3});
  type StopReceipt = Awaited<ReturnType<typeof session.stopPerformanceReplay>>;
  const first = deferred<StopReceipt>(), terminal = deferred<StopReceipt>();
  vi.mocked(session.stopPerformanceReplay).mockImplementationOnce(() => first.promise)
    .mockImplementationOnce(() => terminal.promise);
  await userEvent.click(screen.getByRole("button", {name: `Replay ${SAVED_TAKE.name}`}));
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("0 / 4 events");
  await act(() => f.controller.refreshReplay());
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("3 / 4 events");
  expect(screen.getByRole("button", {name: `Replay ${SAVED_TAKE.name}`}).hasAttribute("disabled")).toBe(true);
  await userEvent.click(screen.getByRole("button", {name: "Stop Replay"}));
  expect(screen.getByRole("heading", {name: "Stopping Replay…"})).not.toBeNull();
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
  first.resolve({...REPLAY_PLAYING, eventCursor: 3, requestId: "stop-1", replayed: false});
  await waitFor(() => expect(session.stopPerformanceReplay).toHaveBeenCalledTimes(2));
  expect(screen.getByRole("button", {name: "Stop Replay"}).hasAttribute("disabled")).toBe(true);
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
  terminal.resolve({...REPLAY_PLAYING, eventCursor: 3, state: "stopped", requestId: "stop-2", replayed: false});
  await screen.findByText("Neutral reset confirmed · HOLD off");
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("3 / 4 events");
  expect(screen.getByRole("status", {name: "Replay status"}).textContent).toContain("stopped · neutral");
});

test("a failed Replay Stop keeps the same owner and progress available for explicit retry", async () => {
  const {fixture: f} = await replaySurfaceFixture({maximumStatusQueries: 1});
  const session = f.runtime.session;
  vi.mocked(session.beginPerformanceReplay).mockResolvedValue({...REPLAY_PLAYING, eventCursor: 2});
  vi.mocked(session.stopPerformanceReplay).mockRejectedValueOnce(new Error("Stop unavailable"))
    .mockResolvedValue({...REPLAY_PLAYING, state: "stopped", eventCursor: 2,
      requestId: "stop-retry", replayed: false});
  await userEvent.click(screen.getByRole("button", {name: `Replay ${SAVED_TAKE.name}`}));
  await userEvent.click(screen.getByRole("button", {name: "Stop Replay"}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Stop Replay"}).hasAttribute("disabled")).toBe(false));
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("2 / 4 events");
  expect(screen.queryByText(/Neutral reset confirmed/)).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Stop Replay"}));
  await screen.findByText("Neutral reset confirmed · HOLD off");
  expect(session.beginPerformanceReplay).toHaveBeenCalledTimes(1);
  expect(vi.mocked(session.stopPerformanceReplay).mock.calls.map(([r]) => r.replayId)).toEqual(["replay-1", "replay-1"]);
});

test("natural Replay completion renders the Core terminal cursor and neutral fact without a synthetic Stop", async () => {
  const {fixture: f} = await replaySurfaceFixture();
  vi.mocked(f.runtime.session.beginPerformanceReplay).mockResolvedValue(REPLAY_PLAYING);
  vi.mocked(f.runtime.session.queryPerformanceReplayStatus).mockResolvedValue({...REPLAY_PLAYING,
    state: "complete", eventCursor: 4});
  await userEvent.click(screen.getByRole("button", {name: `Replay ${SAVED_TAKE.name}`}));
  await act(() => f.controller.refreshReplay());
  expect(screen.getByRole("heading", {name: "Replay complete"})).not.toBeNull();
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("4 / 4 events");
  expect(screen.getByText("Neutral reset confirmed · HOLD off")).not.toBeNull();
  expect(f.runtime.session.stopPerformanceReplay).not.toHaveBeenCalled();
});

test("an empty Replay's actual terminal begin receipt confirms reset without fabricating a status or Stop", async () => {
  const {fixture: f} = await replaySurfaceFixture();
  vi.mocked(f.runtime.session.beginPerformanceReplay).mockResolvedValue({...REPLAY_PLAYING,
    state: "complete", eventCount: 0});
  await userEvent.click(screen.getByRole("button", {name: `Replay ${SAVED_TAKE.name}`}));
  expect(screen.getByRole("heading", {name: "Replay complete"})).not.toBeNull();
  expect(screen.getByRole("status", {name: "Replay events"}).textContent).toBe("0 / 0 events");
  expect(screen.getByText("Neutral reset confirmed · HOLD off")).not.toBeNull();
  expect(f.runtime.session.stopPerformanceReplay).not.toHaveBeenCalled();
  expect(f.runtime.session.queryPerformanceReplayStatus).not.toHaveBeenCalled();
});

test("Replay refuses a failed saved-list snapshot until the explicit retry succeeds", async () => {
  const {fixture: f} = await replaySurfaceFixture();
  vi.mocked(f.runtime.session.listPerformanceRecovery).mockRejectedValueOnce(new Error("recovery unavailable"));
  await act(async () => {await expect(f.controller.refreshPerformances()).rejects.toThrow("recovery unavailable");});
  expect(screen.getByText("Saved Takes unavailable")).not.toBeNull();
  expect(screen.queryByRole("button", {name: `Replay ${SAVED_TAKE.name}`})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Retry saved Takes"}));
  await screen.findByRole("button", {name: `Replay ${SAVED_TAKE.name}`});
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
});

test("Replay hides a replaced Project's saved cards before its new owner read settles", async () => {
  const f = controllerFixture();
  const list = vi.mocked(f.runtime.session.listPerformances);
  list.mockResolvedValue([SAVED_TAKE]);
  const view = render(<PerformSurface controller={f.controller} project={project} bank={0} />);
  selectPerformPage("Replay");
  await screen.findByRole("button", {name: `Replay ${SAVED_TAKE.name}`});
  const next = deferred<readonly PerformanceSummary[]>();
  list.mockReturnValueOnce(next.promise);
  const newProject = {...project, revision: 8};
  f.setCreatorState(creatorState({project: {phase: "ready", projects: [], current: newProject}}));
  view.rerender(<PerformSurface controller={f.controller} project={newProject} bank={0} />);
  await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  expect(screen.queryByRole("button", {name: `Replay ${SAVED_TAKE.name}`})).toBeNull();
  next.resolve([{...SAVED_TAKE, name: "Current owner's Take"}]);
  await screen.findByRole("button", {name: "Replay Current owner's Take"});
  expect(f.controller.getState().performancesOwner).toBe(newProject);
  expect(f.runtime.session.beginPerformanceReplay).not.toHaveBeenCalled();
});
