import {IDBFactory, IDBObjectStore} from "fake-indexeddb";
import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import {expect, test, vi} from "vitest";
import type {MonitorOutputSession} from "@lmdj/web-runtime-platform/runtime_types";

import {App} from "../src/app";
import type {CreatorRuntimeSession, ProjectView, RuntimeHostState} from "../src/runtime/runtime_types";
import {initialCreatorState} from "../src/state/creator_state";
import {readMonitorVolumePreference, writeMonitorVolumePreference} from "../src/state/monitor_volume_preference";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 7, bpm: 120, assetCount: 0, assignedPadCount: 0,
  bundleDigest: "a".repeat(64), key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({
    slot, assetId: null, category: null, colourOverride: null, colour: null,
  })),
  patterns: [{patternId: "22222222-2222-4222-8222-222222222222", bars: 1, events: []}],
  patternSlots: Array<string | null>(16).fill(null),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};
const ready = {
  ...initialCreatorState,
  project: {phase: "ready" as const, projects: [], current: project},
  runtime: {phase: "ready" as const, errorCode: null},
};

// The real App capability checks and Perform controller run here. The fixture
// has no AudioNode: the existing Session monitor producer is observed at its
// documented synchronous boundary, rather than rebuilding its audio graph.
function sessionFixture({monitor = true}: {monitor?: boolean} = {}) {
  let level = 100;
  let terminal = false;
  const hostListeners = new Set<(state: RuntimeHostState) => void>();
  const mutation = vi.fn(async () => {throw new Error("No authoring command is expected");});
  const fx = vi.fn(async () => ({applied: true as const}));
  const event = vi.fn(async () => {throw new Error("No Performance event is expected");});
  const activate = vi.fn(async () => true);
  const close = vi.fn(async () => true);
  const setMonitorVolume = vi.fn((value: number) => {
    if (terminal) throw Object.assign(new Error("Monitor closed"), {code: "HOST_STATE_INVALID"});
    level = value;
  });
  const captureStatus = {
    state: "ready" as const,
    config: {performRecordingFrames: 86_400_000, performRecordingQueueBatches: 32},
    error: null,
  };
  const session: CreatorRuntimeSession = {
    start: async () => true, close,
    listLocalProjects: async () => [project],
    importProject: mutation, duplicateProject: mutation, createProject: mutation,
    openProject: async () => ({}), reloadSnapshot: async () => ({}),
    inspectProject: async () => ({project_revision: project.revision, project: {
      contract: "lmdj.project.v3", project_id: project.projectId,
      revision: project.revision, bpm: project.bpm, assets: {},
      banks: Array.from({length: 4}, (_, bank) => ({bank,
        pads: Array.from({length: 16}, (_, pad) => ({pad, asset_id: null,
          category: null, colour_override: null, colour: null})),
      })),
      patterns: {[project.patternId]: {bars: 1, events: []}},
      sequence_settings: {quantize_enabled: true, swing_percent: 50},
    }}),
    activateAudio: activate, suspendAudio: async () => true,
    trigger: vi.fn(async () => false as const), requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: (listener) => {
      hostListeners.add(listener);
      return () => {hostListeners.delete(listener);};
    },
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended", error_code: null, error_details: {},
      product_build: "9.8.7.6", host_id: "creator-web", host_version: "1.5.0",
      platform_version: "0.3.6", protocol_version: 1,
      capabilities: {secureContext: true, crossOriginIsolated: true,
        sharedArrayBuffer: true, webAssembly: true, audioWorklet: true,
        opfs: true, opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false},
      trigger_admitted_count: 0, trigger_outcome_count: 0, trigger_rejected_count: 0,
    }),
  };
  Object.assign(session, {
    inspectSample: async () => ({projectRevision: project.revision, slot: 0,
      assetId: null, metadata: null, waveformCacheIdentity: null,
      playback: {trimStartFrame: 0, trimEndFrame: null, triggerMode: "one_shot",
        gainMillidb: 0, muted: false, reverse: false, pitchCents: 0, pan: 0,
        loopMode: "forward", loopStartFrame: null, loopCrossfadeFrames: 0,
        attackMs: 0, releaseMs: 0, tone: 0, eq: {low: null, mid: null, high: null}},
    }),
    querySampleQuota: async () => ({projectRevision: project.revision, slot: 0,
      bankQuotaBytes: 1_048_576, bankUsedBytes: 0, bankRemainingBytes: 1_048_576,
      projectQuotaBytes: 4_194_304, projectUsedBytes: 0, projectRemainingBytes: 4_194_304,
      effectiveRemainingBytes: 1_048_576, effectiveRemainingFrames: 524_288, consumed: []}),
    sampleIngestLimits: () => ({maxChunkBytes: 1_048_576, maxChannels: 2,
      maxSampleRate: 48_000, maxFrames: 524_288}),
    queryWaveform: mutation, importAssignSample: mutation, updatePad: mutation,
    resetPad: mutation, deletePad: mutation, retryPrepare: mutation,
    setSamplePreview: mutation, clearSamplePreview: vi.fn(async () => true),
    release: vi.fn(async () => true), stopPad: vi.fn(async () => true),
    stopAll: vi.fn(async () => true), subscribeVoiceState: () => () => {},
    performanceMasterCaptureStatus: () => captureStatus,
    subscribePerformanceMasterCaptureStatus: (listener: (status: typeof captureStatus) => void) => {
      listener(captureStatus); return () => {};
    },
    startPerformanceMasterCapture: mutation, beginPerformanceRecording: mutation,
    recordPerformanceEvent: event, applyFxGesture: fx,
    requestPerformancePatternLaunch: mutation, flushPerformanceRecording: mutation,
    stopPerformanceRecording: mutation, queryPerformanceRecordingStatus: mutation,
    assignPatternSlot: mutation, clearPatternSlot: mutation, movePatternSlot: mutation,
    listPerformances: async () => [], inspectPerformance: mutation,
    savePerformance: mutation, discardPerformance: mutation,
    renamePerformance: mutation, deletePerformance: mutation,
    listPerformanceRecovery: async () => [], applyPerformanceRecovery: mutation,
    discardPerformanceRecovery: mutation, bindPerformanceRecording: mutation,
    beginPerformanceReplay: mutation, stopPerformanceReplay: mutation,
    queryPerformanceReplayStatus: mutation, commitPerformanceResample: mutation,
  });
  if (monitor) {
    const output: MonitorOutputSession = {
      monitorVolume: () => level, monitorDestination: () => null, setMonitorVolume,
    };
    Object.assign(session, output);
  }
  return {session, mutation, fx, event, activate, setMonitorVolume,
    level: () => level,
    failMonitor: () => {terminal = true;},
    emitHost: (state: RuntimeHostState) => {
      for (const listener of hostListeners) listener(state);
    },
  };
}

const master = () => screen.getByRole("slider", {name: "MASTER"}) as HTMLInputElement;
const encoder = () => screen.getByRole("button", {name: "Encoder 4 — Output Volume"});

async function openPerform() {
  // The real boot journey reopens the retained Project independently of the
  // monitor preference read. Wait for its ready page key, not just the gain.
  fireEvent.click(await screen.findByRole("button", {name: "Perform"}));
  return await screen.findByRole("slider", {name: "MASTER"});
}

test("MASTER and ENC4 read and update one remembered monitoring value without authoring or FX", async () => {
  const factory = new IDBFactory();
  vi.stubGlobal("indexedDB", factory);
  await writeMonitorVolumePreference(24, factory);
  const fixture = sessionFixture();
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  try {
    await waitFor(() => expect(fixture.setMonitorVolume).toHaveBeenCalledWith(24));
    await openPerform();
    expect(master().value).toBe("24");
    fireEvent.change(master(), {target: {value: "61"}});
    expect(fixture.level()).toBe(61);
    expect(document.querySelector('.encoder-readbacks [data-encoder="4"] dd')?.textContent).toBe("61%");
    fireEvent.keyDown(encoder(), {key: "ArrowDown"});
    expect(master().value).toBe("60");
    expect(fixture.level()).toBe(60);
    expect(await readMonitorVolumePreference(factory)).toBe(60);
    expect(fixture.activate).not.toHaveBeenCalled();
    expect(fixture.mutation).not.toHaveBeenCalled();
    expect(fixture.fx).not.toHaveBeenCalled();
    expect(fixture.event).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(screen.getByText("Rev").nextElementSibling?.textContent).toBe("7");
  } finally {rendered.unmount(); vi.unstubAllGlobals();}
});

test("MASTER has the same endpoints as ENC4 and survives Perform groups and page navigation", async () => {
  const fixture = sessionFixture();
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  try {
    await waitFor(() => expect(encoder()).toHaveProperty("disabled", false));
    await openPerform();
    fireEvent.change(master(), {target: {value: "0"}});
    fireEvent.keyDown(encoder(), {key: "ArrowDown"});
    expect(fixture.level()).toBe(0);
    expect(master().value).toBe("0");
    fireEvent.change(master(), {target: {value: "100"}});
    fireEvent.keyDown(encoder(), {key: "ArrowUp"});
    expect(fixture.level()).toBe(100);
    fireEvent.change(master(), {target: {value: "42"}});
    fireEvent.click(screen.getByRole("button", {name: "FX / MORE"}));
    expect(master().value).toBe("42");
    const hold = screen.getByRole("button", {name: "HOLD"});
    fireEvent.click(hold);
    await waitFor(() => expect(hold.getAttribute("aria-pressed")).toBe("true"));
    fixture.fx.mockClear();
    fireEvent.change(master(), {target: {value: "43"}});
    expect(hold.getAttribute("aria-pressed")).toBe("true");
    expect(fixture.fx).not.toHaveBeenCalled();
    expect(fixture.event).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", {name: "Project"}));
    await openPerform();
    expect(master().value).toBe("43");
  } finally {rendered.unmount();}
});

test("a rejected monitor update preserves the accepted MASTER, ENC4 and device preference", async () => {
  const factory = new IDBFactory();
  vi.stubGlobal("indexedDB", factory);
  await writeMonitorVolumePreference(25, factory);
  const fixture = sessionFixture();
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  try {
    await waitFor(() => expect(fixture.setMonitorVolume).toHaveBeenCalledWith(25));
    await openPerform();
    fixture.failMonitor();
    fireEvent.change(master(), {target: {value: "63"}});
    expect(fixture.setMonitorVolume).toHaveBeenLastCalledWith(63);
    expect(master().value).toBe("25");
    expect(document.querySelector('.encoder-readbacks [data-encoder="4"] dd')?.textContent).toBe("25%");
    expect(await readMonitorVolumePreference(factory)).toBe(25);
  } finally {rendered.unmount(); vi.unstubAllGlobals();}
});

test("a Perform session without monitoring exposes a disabled MASTER", async () => {
  const fixture = sessionFixture({monitor: false});
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  try {
    await openPerform();
    expect(master()).toHaveProperty("disabled", true);
    expect(encoder()).toHaveProperty("disabled", true);
    fireEvent.change(master(), {target: {value: "42"}});
    expect(fixture.setMonitorVolume).not.toHaveBeenCalled();
  } finally {rendered.unmount();}
});

test("reopening the App restores the last MASTER value including zero", async () => {
  const factory = new IDBFactory();
  vi.stubGlobal("indexedDB", factory);
  const first = sessionFixture();
  let rendered = render(<App initialState={ready} runtimeFactory={() => first.session} />);
  try {
    await waitFor(() => expect(encoder()).toHaveProperty("disabled", false));
    await openPerform();
    fireEvent.change(master(), {target: {value: "0"}});
    expect(await readMonitorVolumePreference(factory)).toBe(0);
    rendered.unmount();
    const second = sessionFixture();
    rendered = render(<App initialState={ready} runtimeFactory={() => second.session} />);
    await waitFor(() => expect(second.setMonitorVolume).toHaveBeenCalledWith(0));
    await openPerform();
    expect(master().value).toBe("0");
    expect(master()).toHaveProperty("disabled", false);
    expect(second.level()).toBe(0);
  } finally {rendered.unmount(); vi.unstubAllGlobals();}
});

test("a retired preference read cannot enable MASTER in its replacement Session", async () => {
  const factory = new IDBFactory();
  vi.stubGlobal("indexedDB", factory);
  await writeMonitorVolumePreference(0, factory);
  const pending: (() => void)[] = [];
  const get = IDBObjectStore.prototype.get;
  const reads = vi.spyOn(IDBObjectStore.prototype, "get").mockImplementation(function (
    this: IDBObjectStore, key,
  ) {
    const request = get.call(this, key);
    if (key !== "monitor-volume.v1") return request;
    let notify: typeof request.onsuccess = null;
    Object.defineProperty(request, "onsuccess", {
      configurable: true,
      get: () => notify === null ? null : (event: Event) => {
        const callback = notify!;
        pending.push(() => callback.call(request, event));
      },
      set: (callback: typeof request.onsuccess) => {notify = callback;},
    });
    return request;
  });
  const first = sessionFixture();
  const second = sessionFixture();
  let created = 0;
  const sessions = [first.session, second.session];
  const rendered = render(<App initialState={ready} runtimeFactory={() => sessions[created++]!} />);
  try {
    await waitFor(() => expect(pending).toHaveLength(1));
    await openPerform();
    expect(master()).toHaveProperty("disabled", true);
    expect(encoder()).toHaveProperty("disabled", true);
    await act(async () => first.emitHost({state: "restart-required",
      errorCode: "HOST_RESTART_REQUIRED", errorDetails: {}}));
    await waitFor(() => expect(pending).toHaveLength(2));
    await act(async () => {pending.shift()!();});
    expect(first.setMonitorVolume).not.toHaveBeenCalled();
    expect(second.setMonitorVolume).not.toHaveBeenCalled();
    expect(master()).toHaveProperty("disabled", true);
    await act(async () => {pending.shift()!();});
    await waitFor(() => expect(second.setMonitorVolume).toHaveBeenCalledExactlyOnceWith(0));
    expect(first.setMonitorVolume).not.toHaveBeenCalled();
    expect(master().value).toBe("0");
    expect(master()).toHaveProperty("disabled", false);
  } finally {
    rendered.unmount();
    await act(async () => {for (const notify of pending.splice(0)) notify();});
    reads.mockRestore();
    vi.unstubAllGlobals();
  }
});
