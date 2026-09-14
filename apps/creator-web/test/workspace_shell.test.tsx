import {readFileSync} from "node:fs";

import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterAll, beforeAll, expect, test, vi} from "vitest";

import {App} from "../src/app";
import {encodePcm16Wav} from "../src/capture/wav_encoder";
import {SampleSurface} from "../src/components/sample_surface";
import {StatusBar} from "../src/components/status_bar";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import type {
  CreatorRuntimeSession,
  CreatorSampleRuntimeSession,
  CreatorCandidateRuntimeSession,
  CandidateJobView,
  SnapshotPublication,
  LocalProjectSummary,
  RuntimeHostState,
  PadPlayback,
  SampleCommit,
  WaveformEnvelope,
  WaveformQuery,
} from "../src/runtime/runtime_types";

const TEST_PRODUCT_BUILD = "9.8.7.6";

const creatorStyles = readFileSync("src/styles.css", "utf8");
let styleElement: HTMLStyleElement;
let originalOfflineAudioContext: typeof globalThis.OfflineAudioContext | undefined;
beforeAll(() => {
  styleElement = document.createElement("style");
  styleElement.textContent = creatorStyles;
  document.head.append(styleElement);
  originalOfflineAudioContext = globalThis.OfflineAudioContext;
  Object.defineProperty(globalThis, "OfflineAudioContext", {
    configurable: true,
    value: class {
      async decodeAudioData(): Promise<AudioBuffer> {
        const samples = Float32Array.from([0, 0.125, 0.25, 0.5, 0.25, 0, -0.25, -0.5]);
        return {
          length: samples.length,
          numberOfChannels: 1,
          sampleRate: 48_000,
          getChannelData: () => samples,
        } as unknown as AudioBuffer;
      }
    },
  });
});
afterAll(() => {
  styleElement.remove();
  Object.defineProperty(globalThis, "OfflineAudioContext", {
    configurable: true,
    value: originalOfflineAudioContext,
  });
});

function wavFile(name: string): File {
  return new File([
    encodePcm16Wav([Float32Array.from([0, 0.25, -0.25, 0.5, -0.5, 0, 0.125, 0])], 48_000),
  ], name, {type: "audio/wav"});
}

async function commitLongSourceSelection(): Promise<void> {
  await screen.findByRole("button", {name: "Commit selection"});
  await userEvent.click(screen.getByRole("button", {name: "Commit selection"}));
}

const ready: CreatorState = {
  ...initialCreatorState,
  project: {
    phase: "ready",
    projects: [],
    current: {
      projectId: "11111111-1111-4111-8111-111111111111",
      patternId: "22222222-2222-4222-8222-222222222222",
      revision: 4,
      bpm: 120,
      assetCount: 0,
      assignedPadCount: 0,
      bundleDigest: "a".repeat(64),
      key: "—",
      pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null})),
      patterns: [{
        patternId: "22222222-2222-4222-8222-222222222222",
        bars: 1,
      }],
      patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
      sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
    },
  },
  runtime: {phase: "ready", errorCode: null},
};

test("keeps Activate audio disabled when Host readiness is unknown", () => {
  render(<StatusBar state={ready} onActivateAudio={() => {}} />);
  expect(screen.getByRole("button", {name: "Activate audio"})
    .hasAttribute("disabled")).toBe(true);
});

test("enables keyboard-reachable Sample while preserving the other mode states", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  const projectMode = screen.getByRole("button", {name: "Project"});
  expect(projectMode.hasAttribute("disabled")).toBe(false);
  const sampleMode = screen.getByRole("button", {name: "Sample"});
  expect(sampleMode.hasAttribute("disabled")).toBe(false);
  expect(sampleMode.tabIndex).toBe(0);
  expect(screen.getByRole("button", {name: "Slice — open a Project with candidate support"})
    .hasAttribute("disabled")).toBe(true);
  const sequenceMode = screen.getByRole("button", {
    name: "Sequence — open a playable Project first",
  });
  expect(sequenceMode.hasAttribute("disabled")).toBe(true);
  const performMode = screen.getByRole("button", {
    name: "Perform — requires a playable Project, running audio, and capture storage",
  });
  expect(performMode.hasAttribute("disabled")).toBe(true);
  expect(performMode.tabIndex).toBe(-1);

  expect(screen.getByText("Key").nextElementSibling?.textContent).toBe("—");
  expect(screen.queryByText(/untitled/i)).toBeNull();
  expect(screen.queryByText(/beat\.lmdj/i)).toBeNull();
  const keys = [
    "Q", "W", "E", "R", "T", "Y", "U", "I",
    "A", "S", "D", "F", "G", "H", "J", "K",
  ];
  for (const [index, key] of keys.entries()) {
    expect(screen.getByRole("button", {
      name: `Pad A${index + 1} — empty — Key ${key}`,
    })).toBeTruthy();
  }
  expect(Array.from(document.querySelectorAll(".pad kbd"), (key) => key.textContent))
    .toEqual(keys);

  // Without a Runtime session the Activate handler is detached, so the
  // action is disabled instead of offering a gesture that cannot run.
  expect(screen.getByRole("button", {name: "Activate audio"})
    .hasAttribute("disabled")).toBe(true);
  const hardwareLayout = screen.getByRole("button", {name: "Hardware layout"});
  await user.tab();
  expect(document.activeElement).toBe(hardwareLayout);
  await user.tab();
  expect(document.activeElement).toBe(projectMode);
  await user.tab();
  expect(document.activeElement).toBe(sampleMode);
  await user.keyboard("{Enter}");
  expect(sampleMode.getAttribute("aria-current")).toBe("page");
  expect(projectMode.hasAttribute("aria-current")).toBe(false);
  expect(screen.getByRole("heading", {name: "Sample editor"})).toBeTruthy();
  expect(screen.getAllByRole("button", {
    name: /^Pad A(?:[1-9]|1[0-6]) — empty$/,
  })).toHaveLength(16);
  expect(screen.getByRole("button", {name: "Bank A"})).toBeTruthy();

  await user.click(projectMode);
  expect(projectMode.getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("heading", {name: "Project 11111111"})).toBeTruthy();
});

test("orders assigned Pad metadata, waveform, controls, Bank, and all Pads", async () => {
  const assetId = "33333333-3333-4333-8333-333333333333";
  const sampleReady: CreatorState = {
    ...ready,
    project: {
      ...ready.project,
      current: {
        ...ready.project.current!,
        assetCount: 1,
        assignedPadCount: 1,
        pads: ready.project.current!.pads.map((pad) =>
          pad.slot === 0 ? {...pad, assetId} : pad
        ),
      },
    },
    audio: {phase: "suspended"},
    sample: {
      ...ready.sample,
      selectedSlot: 0,
      inspect: {
        projectRevision: 4,
        slot: 0,
        assetId,
        playback: {
          trimStartFrame: 0,
          trimEndFrame: 8,
          triggerMode: "one_shot",
          gainMillidb: 0,
          muted: false,
        },
        metadata: {sampleRate: 48_000, channels: 1, sourceFrames: 8},
        waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/2`,
      },
      waveform: {
        metadata: {sampleRate: 48_000, channels: 1, sourceFrames: 8},
        algorithmVersion: 1,
        buckets: [
          {startFrame: 0, endFrame: 4, peakMagnitude: 16_384},
          {startFrame: 4, endFrame: 8, peakMagnitude: 32_768},
        ],
        projectRevision: 4,
      },
      viewport: {sourceFrames: 8, startFrame: 0, endFrame: 8},
      savedRevision: 4,
      runtimeRevision: 4,
    },
  };
  render(<App initialState={sampleReady} />);
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));

  const metadata = screen.getByText("Asset 33333333").closest(".selected-sample")!;
  const waveform = screen.getByRole("region", {name: "Pad A1 waveform editor"});
  const controls = screen.getByRole("region", {name: "Pad A1 Sample controls"});
  const pads = screen.getByRole("region", {name: "Sample Pads"});
  expect(metadata.compareDocumentPosition(waveform) & Node.DOCUMENT_POSITION_FOLLOWING)
    .not.toBe(0);
  expect(waveform.compareDocumentPosition(controls) & Node.DOCUMENT_POSITION_FOLLOWING)
    .not.toBe(0);
  expect(controls.compareDocumentPosition(pads) & Node.DOCUMENT_POSITION_FOLLOWING)
    .not.toBe(0);
  expect(screen.getByRole("button", {name: "Replace Sample"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Record Sample"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Reset Pad to Defaults"})).toBeTruthy();
  expect(screen.getByText("Activate Audio to preview")).toBeTruthy();
  const visiblePads = screen.getAllByRole("button", {
    name: /^Pad A(?:[1-9]|1[0-6]) — (?:assigned|empty)$/,
  });
  expect(visiblePads).toHaveLength(16);
  for (const pad of visiblePads) {
    expect(getComputedStyle(pad).minHeight).toBe("84px");
  }
});

test("bounds and escapes Replace display names, warns, cancels, and restores focus", async () => {
  const assigned: CreatorState = {
    ...ready,
    project: {
      ...ready.project,
      current: {
        ...ready.project.current!,
        assetCount: 1,
        assignedPadCount: 1,
        pads: ready.project.current!.pads.map((pad) => pad.slot === 0
          ? {...pad, assetId: "33333333-3333-4333-8333-333333333333"}
          : pad),
      },
    },
  };
  render(<App initialState={assigned} />);
  const sampleMode = screen.getByRole("button", {name: "Sample"});
  await userEvent.click(sampleMode);
  const pad = screen.getByRole("button", {name: "Pad A1 — assigned"});
  pad.focus();
  const sourceName = `${"<img src=x onerror=private>".repeat(8)}.wav`;
  fireEvent.drop(pad, {
    dataTransfer: {files: [wavFile(sourceName)]},
  });

  const dialog = screen.getByRole("dialog", {name: "Replace Pad A1?"});
  const cancel = screen.getByRole("button", {name: "Cancel replace"});
  const confirm = screen.getByRole("button", {name: "Confirm replace"});
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(cancel);
  expect(sampleMode.closest("[inert]")).not.toBeNull();
  const displayedName = dialog.querySelector("p")?.textContent ?? "";
  expect(Array.from(displayedName)).toHaveLength(96);
  expect(displayedName.endsWith("…")).toBe(true);
  expect(dialog.querySelector("img")).toBeNull();
  expect(dialog.textContent).toContain(
    "Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.",
  );

  confirm.focus();
  fireEvent.keyDown(dialog, {key: "Tab"});
  expect(document.activeElement).toBe(cancel);
  fireEvent.keyDown(dialog, {key: "Escape"});
  expect(screen.queryByRole("dialog", {name: "Replace Pad A1?"})).toBeNull();
  expect(document.activeElement).toBe(pad);
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(screen.getByText("4", {selector: ".project-summary dd"})).toBeTruthy();
});

test("Record on an assigned Pad confirms the replacement before the panel opens", async () => {
  const fixture = mutableSampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");

  // S8-D12: recording onto an assigned Pad is a replacement, so the existing
  // confirmation runs before the microphone is ever requested (S8B-D2).
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  expect(screen.queryByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeNull();
  const dialog = screen.getByRole("dialog", {name: "Replace Pad A1?"});
  expect(dialog.textContent).toContain(
    "Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.",
  );

  await userEvent.click(screen.getByRole("button", {name: "Cancel replace"}));
  expect(screen.queryByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeNull();

  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
  expect(screen.getByRole("dialog", {name: "Pad A1 Pad Capture"})).toBeTruthy();
});

test("Record on an empty Pad opens the capture panel with no replacement prompt", async () => {
  const fixture = mutableSampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));

  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  expect(screen.queryByRole("dialog", {name: "Replace Pad A2?"})).toBeNull();
  expect(screen.getByRole("dialog", {name: "Pad A2 Pad Capture"})).toBeTruthy();

  await userEvent.click(screen.getByRole("button", {name: "Close"}));
  expect(screen.queryByRole("dialog", {name: "Pad A2 Pad Capture"})).toBeNull();
});

test("audio recovery keeps an open capture panel instead of discarding it", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  // Two independent subscribers exist (the shell status bar and the Runtime
  // context that owns recovery readiness), so the fixture must fan out to all
  // of them; keeping only the last one silently starves the recovery path.
  const diagnosticsListeners:
    ((value: ReturnType<CreatorRuntimeSession["diagnostics"]>) => void)[] = [];
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  fixture.session.subscribeDiagnostics = (listener) => {
    diagnosticsListeners.push(listener);
    return () => {};
  };
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await act(async () => hostListener?.({
    state: "running", errorCode: null, errorDetails: {},
  }));
  await screen.findByText("Audio running");

  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  const dialog = screen.getByRole("dialog", {name: "Pad A2 Pad Capture"});

  // A real macOS Safari focus loss interrupts the AudioContext, so the Runtime
  // reports recovery in the same moment the panel's own blur listener stops
  // the recording and retains the take. Tearing the panel down here discards
  // that take with no way to commit or discard it (#738); releasing decoded
  // long-source memory is the only thing recovery owns here.
  await act(async () => hostListener?.({
    state: "interrupted", errorCode: null, errorDetails: {},
  }));
  await screen.findByText("Audio suspended");
  await act(async () => hostListener?.({
    state: "recovering", errorCode: null, errorDetails: {},
  }));
  await act(async () => {
    const probeReady = {
      ...fixture.session.diagnostics(),
      state: "recovering" as const,
      recovery_probe_ready: true,
    };
    for (const listener of diagnosticsListeners) listener(probeReady);
  });
  await screen.findByText("Audio recovering");

  // Identity, not just presence: a remounted panel would be a fresh element
  // with fresh state, which is the same loss of the take by another route.
  // Keeping the node keeps whatever phase the blur listener left it in, and
  // `capture_panel.test.tsx` owns the proof that a blur stop retains the take
  // behind CAPTURE_BLUR_STOP_MESSAGE with Commit and Discard reachable.
  expect(screen.getByRole("dialog", {name: "Pad A2 Pad Capture"})).toBe(dialog);
  expect(dialog.isConnected).toBe(true);
});

const listedSummary: LocalProjectSummary = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 3,
  bpm: 120,
  assetCount: 1,
  assignedPadCount: 1,
  bundleDigest: "a".repeat(64),
};

function runtimeFixture(overrides: Partial<CreatorRuntimeSession> = {}) {
  const calls: string[] = [];
  const session: CreatorRuntimeSession = {
    start: async () => { calls.push("start"); return true; },
    close: async () => { calls.push("close"); return true; },
    listLocalProjects: async () => {
      calls.push("listLocalProjects");
      return [listedSummary];
    },
    importProject: async (_file, {onProgress}) => {
      calls.push("importProject");
      onProgress({completedBytes: 6, totalBytes: 6});
      return listedSummary;
    },
    openProject: async () => { calls.push("openProject"); return {}; },
    inspectProject: async () => {
      calls.push("inspectProject");
      return {
        project_revision: 3,
        project: {
          contract: "lmdj.project.v3",
          project_id: listedSummary.projectId,
          revision: 3,
          bpm: 120,
          assets: {"33333333-3333-4333-8333-333333333333": {artifact: {}}},
          banks: Array.from({length: 4}, (_, bank) => ({
            bank,
            pads: Array.from({length: 16}, (_, pad) => ({
              pad,
              asset_id: bank === 0 && pad === 0
                ? "33333333-3333-4333-8333-333333333333"
                : null,
            })),
          })),
          patterns: {[listedSummary.patternId]: {bars: 1, events: []}},
          sequence_settings: {quantize_enabled: true, swing_percent: 50},
        },
      };
    },
    reloadSnapshot: async () => { calls.push("reloadSnapshot"); return {}; },
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false,
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: () => () => {},
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended",
      error_code: null,
      error_details: {},
      product_build: TEST_PRODUCT_BUILD,
      host_id: "creator-web",
      host_version: "1.5.0",
      platform_version: "0.3.6",
      protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
    ...overrides,
  };
  return {calls, session};
}

function sampleRuntimeFixture(
  overrides: Partial<CreatorSampleRuntimeSession> = {},
) {
  const base = runtimeFixture();
  const queries: WaveformQuery[] = [];
  const inspect = {
    projectRevision: 3,
    slot: 0,
    assetId: "33333333-3333-4333-8333-333333333333",
    playback: {
      trimStartFrame: 0,
      trimEndFrame: 8,
      triggerMode: "gate" as const,
      gainMillidb: 0,
      muted: false,
    },
    metadata: {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 8},
    waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/1`,
  };
  const waveformFor = ({window}: WaveformQuery): WaveformEnvelope => {
    const frameCount = window.endFrame - window.startFrame;
    const framesPerBucket = Math.ceil(frameCount / window.bucketCount);
    return {
      metadata: inspect.metadata,
      algorithmVersion: 1,
      buckets: Array.from(
        {length: Math.ceil(frameCount / framesPerBucket)},
        (_, index) => ({
          startFrame: window.startFrame + index * framesPerBucket,
          endFrame: Math.min(
            window.endFrame,
            window.startFrame + (index + 1) * framesPerBucket,
          ),
          peakMagnitude: index % 2 === 0 ? 16_384 : 32_768,
        }),
      ),
      projectRevision: inspect.projectRevision,
    };
  };
  const session: CreatorSampleRuntimeSession = {
    ...base.session,
    querySampleQuota: async (slot) => ({
      projectRevision: 3, slot, bankQuotaBytes: 67_108_864,
      bankUsedBytes: 0, bankRemainingBytes: 67_108_864,
      projectQuotaBytes: 134_217_728, projectUsedBytes: 0,
      projectRemainingBytes: 134_217_728,
      effectiveRemainingBytes: 67_108_864,
      effectiveRemainingFrames: 16_777_216, consumed: [],
    }),
    sampleIngestLimits: () => ({
      sourceBytes: 104_857_600, decodedFrames: 43_200_000,
      channels: 2, artifactBytes: 68_157_440,
    }),
    inspectSample: async () => {
      base.calls.push("inspectSample");
      return inspect;
    },
    queryWaveform: async (request) => {
      queries.push(request);
      return waveformFor(request);
    },
    importAssignSample: async () => ({
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    }),
    updatePad: async () => ({
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    }),
    resetPad: async () => ({
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    }),
    setSamplePreview: async () => true,
    clearSamplePreview: async () => true,
    release: async () => true,
    stopPad: async () => true,
    stopAll: async () => true,
    retryPrepare: async (patternId) => ({
      projectId: listedSummary.projectId,
      projectRevision: 3,
      patternId,
      runtimeReady: true,
      generation: 1,
      snapshotError: null,
      runtimeRevision: 3,
    }),
    subscribeVoiceState: () => () => {},
    ...overrides,
  };
  return {...base, inspect, queries, session};
}

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  let reject: (reason: unknown) => void = () => {};
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return {promise, resolve, reject};
}

async function flushAsyncTurns(turns = 40) {
  await act(async () => {
    for (let turn = 0; turn < turns; ++turn) await Promise.resolve();
  });
}

function mutableSampleRuntimeFixture() {
  const assigned = new Map<number, string>([
    [0, "33333333-3333-4333-8333-333333333333"],
  ]);
  const playbacks = new Map<number, Readonly<PadPlayback>>([
    [0, Object.freeze({
      trimStartFrame: 0,
      trimEndFrame: 8,
      triggerMode: "gate",
      gainMillidb: 0,
      muted: false,
    })],
  ]);
  let revision = 3;
  const digest = () => "abcdef"[Math.min(5, Math.max(0, revision - 3))]!.repeat(64);
  const summary = (): LocalProjectSummary => ({
    ...listedSummary,
    revision,
    assetCount: new Set(assigned.values()).size,
    assignedPadCount: assigned.size,
    bundleDigest: digest(),
  });
  const inspectSample = (slot: number) => {
    const assetId = assigned.get(slot) ?? null;
    const playback = playbacks.get(slot) ?? {
      trimStartFrame: 0,
      trimEndFrame: assetId === null ? null : 8,
      triggerMode: "one_shot" as const,
      gainMillidb: 0,
      muted: false,
    };
    return {
      projectRevision: revision,
      slot,
      assetId,
      playback,
      metadata: assetId === null
        ? null
        : {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 8},
      waveformCacheIdentity: assetId === null
        ? null
        : `${digest()}/1/max-abs-mirror/1`,
    };
  };
  const inspectProject = () => ({
    project_revision: revision,
    project: {
      contract: "lmdj.project.v3",
      project_id: listedSummary.projectId,
      revision,
      bpm: listedSummary.bpm,
      assets: Object.fromEntries([...new Set(assigned.values())].map((assetId) => [
        assetId,
        {artifact: {}},
      ])),
      banks: Array.from({length: 4}, (_, bank) => ({
        bank,
        pads: Array.from({length: 16}, (_, pad) => ({
          pad,
          asset_id: assigned.get(bank * 16 + pad) ?? null,
        })),
      })),
      patterns: {[listedSummary.patternId]: {bars: 1, events: []}},
      sequence_settings: {quantize_enabled: true, swing_percent: 50},
    },
  });
  const fixture = sampleRuntimeFixture({
    listLocalProjects: async () => [summary()],
    inspectProject: async () => inspectProject(),
    inspectSample: async (slot) => inspectSample(slot),
    queryWaveform: async ({slot, window}) => {
      const inspected = inspectSample(slot);
      if (inspected.metadata === null) throw new TypeError("Sample is empty");
      const frameCount = window.endFrame - window.startFrame;
      const framesPerBucket = Math.ceil(frameCount / window.bucketCount);
      return {
        metadata: inspected.metadata,
        algorithmVersion: 1,
        buckets: Array.from(
          {length: Math.ceil(frameCount / framesPerBucket)},
          (_, index) => ({
            startFrame: window.startFrame + index * framesPerBucket,
            endFrame: Math.min(
              window.endFrame,
              window.startFrame + (index + 1) * framesPerBucket,
            ),
            peakMagnitude: 16_384,
          }),
        ),
        projectRevision: inspected.projectRevision,
      };
    },
  });
  return {
    ...fixture,
    assigned,
    playbacks,
    summary,
    inspectSample,
    inspectProject,
    get revision() { return revision; },
    set revision(value: number) { revision = value; },
  };
}

async function candidatePlaybackFixture() {
  const fixture = mutableSampleRuntimeFixture();
  const sourceId = "33333333-3333-4333-8333-333333333333";
  const adoptedId = "44444444-4444-4444-8444-444444444444";
  const projectId = listedSummary.projectId;
  const job: CandidateJobView = {job_id: `slice-${projectId}-${sourceId}`,
    active_set_id: "set", history: [], sets: [{set_id: "set", status: "active",
      attempt_id: "attempt", source: {project_id: projectId, asset_id: sourceId, project_revision: 3},
      recipes: [{candidate_id: "recipe", kind: "slice_interval_v1", start_frame: 0, end_frame: 8, frame_rate: 48000}]}]};
  const publication = (): SnapshotPublication => ({projectId, patternId: listedSummary.patternId,
    projectRevision: fixture.revision, runtimeRevision: fixture.revision,
    runtimeReady: true, generation: 2, snapshotError: null});
  const prepare = vi.fn(async (_patternId: string) => publication());
  const trigger = vi.fn(async () => false);
  const adopt = vi.fn(async (request: Parameters<CreatorCandidateRuntimeSession["adoptCandidates"]>[0]) => {
    fixture.revision += 1;
    fixture.assigned.set(1, adoptedId);
    return {project_revision: fixture.revision, set_id: "set",
      adopted: request.selections.map(selection => ({...selection, asset_id: adoptedId}))};
  });
  const session = Object.assign(fixture.session, {
    inspectProject: async () => {
      const value = fixture.inspectProject();
      for (const asset of Object.values(value.project.assets)) asset.artifact = {
        sha256: "a".repeat(64), byte_length: 60, media_type: "audio/wav"};
      return value;
    },
    listProviders: async () => ({providers: [], granted_permissions: []}),
    configureProviderPermissions: async () => ({granted_permissions: []}),
    selectProvider: async () => ({}),
    inspectCandidateJob: async () => job,
    runCandidateJob: async () => job,
    cancelCandidateJob: async () => job,
    discardCandidateSet: async () => job,
    auditionCandidate: async () => ({project_revision: 3, played: false}),
    stopCandidateAudition: async () => ({}),
    adoptCandidates: adopt,
    retryPrepare: prepare,
    reloadSnapshot: async (patternId: string) => {
      fixture.calls.push("reloadSnapshot");
      if (fixture.revision === 3) return {};
      const value = await prepare(patternId);
      if (!value.runtimeReady) throw new Error(value.snapshotError?.message ?? "Not ready");
      return {project_id: value.projectId, project_revision: value.projectRevision,
        pattern_id: value.patternId, runtime_ready: true, generation: value.generation,
        snapshot_error: null};
    },
    trigger,
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Slice"}));
  await screen.findByRole("option", {name: /Source 1/});
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice source"}), sourceId);
  await screen.findByRole("button", {name: "Add target"});
  await userEvent.click(screen.getByRole("button", {name: "Add target"}));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Target 1 slice"}), "recipe");
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Target 1 Bank"}), "0");
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Target 1 Pad"}),
    screen.getByRole("combobox", {name: "Target 1 Pad"}).querySelector('option[value="1"]')!);
  return {...fixture, prepare, trigger, adopt, publication, get revision() {return fixture.revision;}};
}

test("Candidate adoption waits for a new Runtime Bank before reporting playback ready", async () => {
  const fixture = await candidatePlaybackFixture();
  const pending = deferred<SnapshotPublication>();
  fixture.prepare.mockImplementationOnce(() => pending.promise);
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await waitFor(() => expect(fixture.prepare).toHaveBeenCalledWith(listedSummary.patternId));
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
  expect(screen.queryByText("Adopted 1 slices.")).toBeNull();
  expect(screen.getByText("Preparing audio at revision 4…")).toBeTruthy();
  await act(async () => pending.resolve(fixture.publication()));
  expect(await screen.findByText("Adopted 1 slices.")).toBeTruthy();
  expect(screen.queryByRole("region", {name: "Project audio status"})).toBeNull();
});

test("Candidate publication failure retains one commit and retries only preparation", async () => {
  const fixture = await candidatePlaybackFixture();
  fixture.prepare.mockImplementationOnce(async () => ({...fixture.publication(),
    runtimeReady: false, generation: null, runtimeRevision: 3,
    snapshotError: {code: "COOK_FAILED", message: "Runtime preparation failed", details: {}}}));
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  expect(await screen.findByText("Adopted 1 slices.")).toBeTruthy();
  expect(screen.getByText("Saved at revision 4; audio is not ready.")).toBeTruthy();
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
  await userEvent.click(screen.getByRole("button", {name: "Retry audio preparation"}));
  await waitFor(() => expect(fixture.prepare).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.queryByRole("region", {name: "Project audio status"})).toBeNull());
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
});

test.each(["pointer", "keyboard", "midi"])("Candidate preparation blocks %s Pad admission until successful retry", async (source) => {
  const fixture = await candidatePlaybackFixture();
  const midiInput = Object.assign(new EventTarget(), {type: "input", state: "connected", id: "candidate-test"});
  if (source === "midi") {
    const original = Object.getOwnPropertyDescriptor(navigator, "requestMIDIAccess");
    Object.defineProperty(navigator, "requestMIDIAccess", {configurable: true,
      value: async () => ({inputs: new Map([["candidate-test", midiInput]])})});
    try { await userEvent.click(screen.getByRole("button", {name: "Enable MIDI"})); }
    finally {
      if (original) Object.defineProperty(navigator, "requestMIDIAccess", original);
      else Reflect.deleteProperty(navigator, "requestMIDIAccess");
    }
  }
  const midiMessage = (status: number) => {
    const event = new Event("midimessage");
    Object.defineProperty(event, "data", {value: new Uint8Array([status, 36, 100])});
    midiInput.dispatchEvent(event);
  };
  await userEvent.click(screen.getByRole("button", {name: "Activate audio"}));
  const pending = deferred<SnapshotPublication>();
  fixture.prepare.mockImplementationOnce(() => pending.promise);
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await screen.findByText("Preparing audio at revision 4…");
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  const pad = screen.getByRole("button", {name: /^Pad A1 — assigned/});
  const press = async () => {
    await act(async () => {
      if (source === "pointer") {
        const event = new MouseEvent("pointerdown", {bubbles: true, button: 0});
        Object.defineProperties(event, {pointerId: {value: 1}, pointerType: {value: "mouse"}, isPrimary: {value: true}});
        fireEvent(pad, event);

      } else if (source === "midi") {
        midiMessage(0x90);
      } else {
        fireEvent.keyDown(window, {key: "q", code: "KeyQ"});

      }
    });
    await act(async () => {
      if (source === "pointer") fireEvent.pointerUp(pad, {pointerId: 1, pointerType: "mouse", button: 0});
      else if (source === "midi") midiMessage(0x80);
      else fireEvent.keyUp(window, {key: "q", code: "KeyQ"});
    });
  };
  await press();
  expect(fixture.trigger).not.toHaveBeenCalled();
  await act(async () => pending.resolve({...fixture.publication(), runtimeReady: false,
    generation: null, runtimeRevision: 3,
    snapshotError: {code: "COOK_FAILED", message: "Not prepared", details: {}}}));
  await screen.findByText("Saved at revision 4; audio is not ready.");
  await press();
  expect(fixture.trigger).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Retry audio preparation"}));
  await waitFor(() => expect(screen.queryByRole("region", {name: "Project audio status"})).toBeNull());
  await press();
  await waitFor(() => expect(fixture.trigger).toHaveBeenCalledTimes(1));
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
});

function busyProjectionFixture(
  source: "project" | "sample",
  busyFailures: number | null,
) {
  const fixture = mutableSampleRuntimeFixture();
  let mutationCount = 0;
  let mutationCommitted = false;
  let resolutionInspectSeen = false;
  let busyCount = 0;
  fixture.session.updatePad = async (request) => {
    mutationCount += 1;
    fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
    fixture.revision = 4;
    mutationCommitted = true;
    return {
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    };
  };
  fixture.session.inspectProject = async () => {
    if (source === "project" && mutationCommitted &&
      (busyFailures === null || busyCount < busyFailures)) {
      busyCount += 1;
      throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
    }
    return fixture.inspectProject();
  };
  fixture.session.inspectSample = async (slot) => {
    const inspected = fixture.inspectSample(slot);
    if (!mutationCommitted || source !== "sample") return inspected;
    if (!resolutionInspectSeen) {
      resolutionInspectSeen = true;
      fixture.revision = 5;
      return inspected;
    }
    if (busyFailures === null || busyCount < busyFailures) {
      busyCount += 1;
      throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
    }
    return inspected;
  };
  return {
    ...fixture,
    get mutationCount() { return mutationCount; },
    get busyCount() { return busyCount; },
  };
}

test("commits composed controlled Volume once per pointer and keyboard completion", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let previewCount = 0;
  let updateCount = 0;
  fixture.session.setSamplePreview = async () => {
    previewCount += 1;
    return true;
  };
  fixture.session.updatePad = async (request) => {
    updateCount += 1;
    fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
    fixture.revision += 1;
    return {
      committedRevision: fixture.revision,
      runtimeRevision: fixture.revision,
      runtimePublished: true,
      snapshotError: null,
    };
  };
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  const volume = screen.getByRole("slider", {name: "Pad A1 Volume"});

  fireEvent.pointerDown(volume, {pointerId: 31});
  fireEvent.change(volume, {target: {value: "-3.2"}});
  await waitFor(() => expect(previewCount).toBe(1));
  expect(updateCount).toBe(0);
  fireEvent.pointerUp(volume, {pointerId: 31});
  await waitFor(() => expect(updateCount).toBe(1));
  await waitFor(() => expect(volume.hasAttribute("disabled")).toBe(false));

  fireEvent.change(volume, {target: {value: "-4.1"}});
  await waitFor(() => expect(previewCount).toBe(2));
  expect(updateCount).toBe(1);
  fireEvent.keyUp(volume, {key: "ArrowLeft"});
  await waitFor(() => expect(updateCount).toBe(2));
});

test.each(["update", "reset"] as const)(
  "settles a slow $kind after selecting a different Pad",
  async (kind) => {
    const fixture = mutableSampleRuntimeFixture();
    const mutation = deferred<SampleCommit>();
    let requestPlayback: Readonly<PadPlayback> | null = null;
    let operationCount = 0;
    fixture.session.importAssignSample = async () => {
      operationCount += 1;
      return mutation.promise;
    };
    fixture.session.updatePad = async (request) => {
      operationCount += 1;
      requestPlayback = request.playback;
      return mutation.promise;
    };
    fixture.session.resetPad = async () => {
      operationCount += 1;
      return mutation.promise;
    };
    const {container} = render(
      <App initialState={ready} runtimeFactory={() => fixture.session} />,
    );
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");

    const selectedAfter = 1;
    if (kind === "update") {
      await userEvent.click(screen.getByRole("button", {name: "Mute"}));
    } else {
      await userEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
      await userEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
    }
    await waitFor(() => expect(operationCount).toBe(1));
    await userEvent.click(screen.getByRole("button", {
      name: `Pad A${selectedAfter + 1} — empty`,
    }));

    if (kind === "update") {
      fixture.playbacks.set(0, requestPlayback!);
    } else {
      fixture.playbacks.set(0, Object.freeze({
        trimStartFrame: 0,
        trimEndFrame: 8,
        triggerMode: "one_shot",
        gainMillidb: 0,
        muted: false,
      }));
    }
    fixture.revision = 4;
    await act(async () => mutation.resolve({
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    }));

    await screen.findByText(`Pad A${selectedAfter + 1}`, {
      selector: ".selected-sample strong",
    });
    await waitFor(() => expect(
      screen.getByRole("button", {name: `Add Sample to Pad A${selectedAfter + 1}`})
        .hasAttribute("disabled"),
    ).toBe(false));
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(screen.getByText("4", {selector: ".project-summary dd"})).toBeTruthy();
  },
);

test("atomically refreshes full Project truth on a real mutation conflict", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let updateCount = 0;
  fixture.session.updatePad = async () => {
    updateCount += 1;
    fixture.assigned.set(1, "44444444-4444-4444-8444-444444444444");
    fixture.revision = 4;
    throw Object.assign(new Error("conflict"), {code: "REVISION_CONFLICT"});
  };
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  await userEvent.click(screen.getByRole("button", {name: "Mute"}));

  expect((await screen.findByRole("alert")).textContent).toBe(
    "Project changed; review and try again",
  );
  expect(updateCount).toBe(1);
  expect(screen.getByRole("button", {name: "Pad A2 — assigned"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(screen.getByText("4", {selector: ".project-summary dd"})).toBeTruthy();
  expect(screen.getByText("2 / 64")).toBeTruthy();
});

test("converges committed Sample and Project truth across interleaved revisions", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let mutationCommitted = false;
  let advancedAfterSampleInspect = false;
  let advancedBetweenProjectReads = false;
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  fixture.session.importAssignSample = async () => {
    fixture.assigned.set(1, "44444444-4444-4444-8444-444444444444");
    fixture.revision = 4;
    mutationCommitted = true;
    return {
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    };
  };
  fixture.session.inspectSample = async (slot) => {
    const inspected = fixture.inspectSample(slot);
    if (mutationCommitted && slot === 1 && !advancedAfterSampleInspect) {
      advancedAfterSampleInspect = true;
      fixture.assigned.set(3, "55555555-5555-4555-8555-555555555555");
      fixture.revision = 5;
    }
    return inspected;
  };
  fixture.session.inspectProject = async () => {
    const inspected = fixture.inspectProject();
    if (advancedAfterSampleInspect && !advancedBetweenProjectReads) {
      advancedBetweenProjectReads = true;
      fixture.assigned.set(4, "66666666-6666-4666-8666-666666666666");
      fixture.revision = 6;
    }
    return inspected;
  };
  const {container} = render(
    <App initialState={ready} runtimeFactory={() => fixture.session} />,
  );
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await act(async () => hostListener?.({
    state: "running",
    errorCode: null,
    errorDetails: {},
  }));
  await screen.findByText("Audio running");
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));
  const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
  await userEvent.upload(input, wavFile("interleaved.wav"));
  await commitLongSourceSelection();

  await screen.findByText("Asset 44444444");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("button", {name: "Pad A4 — assigned"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Pad A5 — assigned"})).toBeTruthy();
  expect(screen.getByText("Audio running")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(screen.getByText("6", {selector: ".project-summary dd"})).toBeTruthy();
  expect(screen.getByText("4 / 64")).toBeTruthy();
  expect(fixture.calls.filter((call) => call === "openProject")).toHaveLength(1);
  expect(fixture.calls.filter((call) => call === "reloadSnapshot")).toHaveLength(1);
});

test.each([
  "NOT_FOUND",
  "HOST_PROTOCOL_MISMATCH",
  "HOST_RESTART_REQUIRED",
] as const)(
  "bounds a committed projection refresh after permanent $code",
  async (code) => {
    const fixture = mutableSampleRuntimeFixture();
    let mutationCommitted = false;
    let projectReads = 0;
    fixture.session.updatePad = async (request) => {
      fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
      fixture.revision = 4;
      mutationCommitted = true;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    fixture.session.inspectProject = async () => {
      if (!mutationCommitted) return fixture.inspectProject();
      projectReads += 1;
      if (code === "HOST_PROTOCOL_MISMATCH") return {project_revision: "invalid"};
      if (code === "HOST_RESTART_REQUIRED") {
        throw Object.assign(new Error("restart"), {code});
      }
      return fixture.inspectProject();
    };
    fixture.session.listLocalProjects = async () =>
      mutationCommitted && code === "NOT_FOUND" ? [] : [fixture.summary()];

    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      await flushAsyncTurns();

      expect(screen.getByText(
        "Sample was saved, but current Project truth could not be refreshed",
      )).toBeTruthy();
      expect(screen.getByText("Creator unavailable")).toBeTruthy();
      expect(screen.getByText(code === "HOST_PROTOCOL_MISMATCH"
        ? "Creator and Runtime could not verify a compatible protocol."
        : code === "HOST_RESTART_REQUIRED"
          ? "Runtime must be restarted before continuing."
          : "Creator cannot continue (NOT_FOUND)."),
      ).toBeTruthy();
      const pad = screen.getByRole("button", {name: "Pad A1 — empty"});
      expect(pad.hasAttribute("disabled")).toBe(true);
      const settledReads = projectReads;
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(projectReads).toBe(settledReads);
      expect(settledReads).toBeGreaterThan(0);
      expect(settledReads).toBeLessThanOrEqual(4);
      expect(screen.queryByText("Sample operation failed")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  },
);

test.each([
  {source: "project" as const, busyFailures: 1},
  {source: "project" as const, busyFailures: 2},
  {source: "sample" as const, busyFailures: 1},
  {source: "sample" as const, busyFailures: 2},
])(
  "retries $busyFailures transient PROJECT_BUSY response(s) from $source inspection",
  async ({source, busyFailures}) => {
    const fixture = busyProjectionFixture(source, busyFailures);
    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");
    await userEvent.click(screen.getByRole("button", {name: "Mute"}));

    await waitFor(() => expect(screen.getByRole("button", {
      name: "Reset Pad to Defaults",
    }).hasAttribute("disabled")).toBe(false));
    expect(fixture.mutationCount).toBe(1);
    expect(fixture.busyCount).toBe(busyFailures);
    expect(screen.queryByRole("alert")).toBeNull();
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(screen.getByText(source === "sample" ? "5" : "4", {
      selector: ".project-summary dd",
    })).toBeTruthy();
  },
);

test.each(["project", "sample"] as const)(
  "bounds persistent PROJECT_BUSY from $source inspection",
  async (source) => {
    const fixture = busyProjectionFixture(source, null);
    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");

    vi.useFakeTimers();
    try {
      fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      await flushAsyncTurns();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      await flushAsyncTurns();

      expect(screen.getByText(
        "Sample was saved, but current Project truth could not be refreshed",
      )).toBeTruthy();
      expect(screen.getByText("Runtime must be restarted before continuing.")).toBeTruthy();
      expect(fixture.mutationCount).toBe(1);
      expect(fixture.busyCount).toBe(4);
      const settledBusyCount = fixture.busyCount;
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(fixture.busyCount).toBe(settledBusyCount);
    } finally {
      vi.useRealTimers();
    }
  },
);

test.each(["update", "reset"] as const)(
  "resumes a committed $kind projection refresh after Sample remount",
  async (kind) => {
    const fixture = mutableSampleRuntimeFixture();
    let mutationCount = 0;
    let mutationCommitted = false;
    let unstableProjection = true;
    let projectionReads = 0;
    const commit = async (): Promise<SampleCommit> => {
      mutationCount += 1;
      fixture.revision = 4;
      mutationCommitted = true;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    fixture.session.updatePad = async (request) => {
      fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
      return commit();
    };
    fixture.session.resetPad = async (request) => {
      fixture.playbacks.set(request.slot, Object.freeze({
        trimStartFrame: 0,
        trimEndFrame: 8,
        triggerMode: "one_shot",
        gainMillidb: 0,
        muted: false,
      }));
      return commit();
    };
    fixture.session.inspectProject = async () => {
      if (mutationCommitted) projectionReads += 1;
      return fixture.inspectProject();
    };
    fixture.session.listLocalProjects = async () => {
      const summary = fixture.summary();
      return [mutationCommitted && unstableProjection
        ? {...summary, revision: summary.revision + 1}
        : summary];
    };

    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");

    vi.useFakeTimers();
    try {
      if (kind === "update") {
        fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      } else {
        fireEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
        fireEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
      }
      await flushAsyncTurns();
      expect(mutationCount).toBe(1);
      expect(projectionReads).toBeGreaterThan(0);

      fireEvent.click(screen.getByRole("button", {name: "Project"}));
      unstableProjection = false;
      fireEvent.click(screen.getByRole("button", {name: "Sample"}));
      await flushAsyncTurns();

      expect(mutationCount).toBe(1);
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.getByRole("button", {name: "Reset Pad to Defaults"})
        .hasAttribute("disabled")).toBe(false);
      fireEvent.click(screen.getByRole("button", {name: "Project"}));
      expect(screen.getByText("4", {selector: ".project-summary dd"})).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  },
);

test("keeps pre-commit Sample import abort ownership on unmount", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let importCount = 0;
  let abortCount = 0;
  fixture.session.importAssignSample = async (_file, options) => {
    importCount += 1;
    return new Promise<SampleCommit>((_resolve, reject) => {
      options.signal?.addEventListener("abort", () => {
        abortCount += 1;
        reject(new DOMException("cancelled", "AbortError"));
      }, {once: true});
    });
  };
  const {container, unmount} = render(
    <App initialState={ready} runtimeFactory={() => fixture.session} />,
  );
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));
  const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
  await userEvent.upload(input, wavFile("abort.wav"));
  await commitLongSourceSelection();
  await waitFor(() => expect(importCount).toBe(1));

  unmount();
  await waitFor(() => expect(abortCount).toBe(1));
  expect(importCount).toBe(1);
});

test("queries bounded multi-resolution Facade windows for local zoom and pan", async () => {
  const fixture = sampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await waitFor(() => expect(fixture.calls).toContain("inspectSample"));
  await waitFor(() => expect(fixture.queries).toEqual([{
    slot: 0,
    window: {startFrame: 0, endFrame: 8, bucketCount: 8},
  }]));

  await userEvent.click(screen.getByRole("button", {name: "Zoom In"}));
  await waitFor(() => expect(fixture.queries[1]).toEqual({
    slot: 0,
    window: {startFrame: 2, endFrame: 6, bucketCount: 4},
  }));
  await userEvent.click(screen.getByRole("button", {name: "Pan Right"}));
  await waitFor(() => expect(fixture.queries[2]).toEqual({
    slot: 0,
    window: {startFrame: 3, endFrame: 7, bucketCount: 4},
  }));
});

test.each(["release", "stopPad", "stopAll", "retryPrepare"] as const)(
  "does not enable the Sample capability when %s is missing",
  async (missing) => {
    let voiceSubscriptions = 0;
    const fixture = sampleRuntimeFixture({
      subscribeVoiceState: () => {
        voiceSubscriptions += 1;
        return () => {};
      },
    });
    const incomplete: Partial<CreatorSampleRuntimeSession> = {...fixture.session};
    delete incomplete[missing];
    const view = render(
      <App runtimeFactory={() => incomplete as CreatorRuntimeSession} />,
    );
    await screen.findByRole("button", {name: "Open Project 11111111"});

    expect(voiceSubscriptions).toBe(0);
    view.unmount();
  },
);

test.each([
  {key: "Enter", code: "Enter"},
  {key: " ", code: "Space"},
])("gives an assigned Pad one $code press/release and suppresses repeat", async ({key, code}) => {
  const triggers: Array<{slot: number; velocity: number; source: string}> = [];
  const releases: Array<{slot: number; source: string}> = [];
  const fixture = sampleRuntimeFixture({
    trigger: async (slot, velocity, source) => {
      triggers.push({slot, velocity, source});
      return {sequence: 1, slot, velocity, source};
    },
    release: async (slot, source) => {
      releases.push({slot, source});
      return true;
    },
  });
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  const pad = screen.getByRole("button", {name: "Pad A1 — assigned"});
  pad.focus();

  fireEvent.keyDown(pad, {key, code, repeat: false});
  fireEvent.keyDown(pad, {key, code, repeat: true});
  await waitFor(() => expect(triggers).toEqual([
    {slot: 0, velocity: 100, source: "keyboard"},
  ]));
  fireEvent.keyUp(pad, {key, code});
  await waitFor(() => expect(releases).toEqual([{slot: 0, source: "keyboard"}]));
});

test("keeps an imported empty Pad assigned and playable after selecting another Pad", async () => {
  const importedAssetId = "44444444-4444-4444-8444-444444444444";
  const replayAssetId = "55555555-5555-4555-8555-555555555555";
  const assigned = new Map<number, string>([
    [0, "33333333-3333-4333-8333-333333333333"],
  ]);
  const triggers: number[] = [];
  const projectionCalls: string[] = [];
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  let revision = 3;
  const summary = (): LocalProjectSummary => ({
    ...listedSummary,
    revision,
    assetCount: assigned.size,
    assignedPadCount: assigned.size,
    bundleDigest: (revision === 3 ? "a" : "b").repeat(64),
  });
  const inspectSample = (slot: number) => ({
    projectRevision: revision,
    slot,
    assetId: assigned.get(slot) ?? null,
    playback: {
      trimStartFrame: 0,
      trimEndFrame: assigned.has(slot) ? 8 : null,
      triggerMode: "gate" as const,
      gainMillidb: 0,
      muted: false,
    },
    metadata: assigned.has(slot)
      ? {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 8}
      : null,
    waveformCacheIdentity: assigned.has(slot)
      ? `${summary().bundleDigest}/1/max-abs-mirror/1`
      : null,
  });
  const fixture = sampleRuntimeFixture({
    listLocalProjects: async () => {
      projectionCalls.push(`list:${revision}`);
      return [summary()];
    },
    inspectProject: async () => {
      projectionCalls.push(`inspect:${revision}`);
      return {
        project_revision: revision,
        project: {
          contract: "lmdj.project.v3",
          project_id: listedSummary.projectId,
          revision,
          bpm: listedSummary.bpm,
          assets: Object.fromEntries([...assigned.values()].map((assetId) => [
            assetId,
            {artifact: {}},
          ])),
          banks: Array.from({length: 4}, (_, bank) => ({
            bank,
            pads: Array.from({length: 16}, (_, pad) => ({
              pad,
              asset_id: assigned.get(bank * 16 + pad) ?? null,
            })),
          })),
          patterns: {[listedSummary.patternId]: {bars: 1, events: []}},
          sequence_settings: {quantize_enabled: true, swing_percent: 50},
        },
      };
    },
    inspectSample: async (slot) => inspectSample(slot),
    queryWaveform: async ({slot, window}) => {
      const inspected = inspectSample(slot);
      if (inspected.metadata === null) throw new TypeError("Sample is empty");
      const frameCount = window.endFrame - window.startFrame;
      const framesPerBucket = Math.ceil(frameCount / window.bucketCount);
      return {
        metadata: inspected.metadata,
        algorithmVersion: 1,
        buckets: Array.from(
          {length: Math.ceil(frameCount / framesPerBucket)},
          (_, index) => ({
            startFrame: window.startFrame + index * framesPerBucket,
            endFrame: Math.min(
              window.endFrame,
              window.startFrame + (index + 1) * framesPerBucket,
            ),
            peakMagnitude: 16_384,
          }),
        ),
        projectRevision: inspected.projectRevision,
      };
    },
    importAssignSample: async (_file, options) => {
      expect(options.slot).toBe(1);
      expect(options.expectedRevision).toBe(3);
      assigned.set(options.slot, importedAssetId);
      assigned.set(3, replayAssetId);
      revision = 5;
      return {
        committedRevision: 4,
        runtimeRevision: 5,
        runtimePublished: true,
        snapshotError: null,
      };
    },
    trigger: async (slot, velocity, source) => {
      triggers.push(slot);
      return {sequence: 1, slot, velocity, source};
    },
    subscribeHostState: (listener) => {
      hostListener = listener;
      return () => {};
    },
    diagnostics: () => ({
      state: "audio-suspended",
      error_code: null,
      error_details: {},
      product_build: "1.0.16.5",
      host_id: "creator-web",
      host_version: "1.0.2",
      platform_version: "0.1.2",
      protocol_version: 1,
      capabilities: {
        secureContext: true,
        crossOriginIsolated: true,
        sharedArrayBuffer: true,
        webAssembly: true,
        audioWorklet: true,
        opfs: true,
        opfsSyncAccessHandle: true,
        opfsWritableReplace: true,
        webMidi: false,
      },
      trigger_admitted_count: 0,
      trigger_outcome_count: 0,
      trigger_rejected_count: 0,
    }),
  });
  const initialState: CreatorState = {
    ...ready,
    project: {
      phase: "ready",
      projects: [summary()],
      current: {
        ...ready.project.current!,
        ...summary(),
        revision: 2,
        assetCount: 1,
        assignedPadCount: 1,
        pads: ready.project.current!.pads.map((pad) => pad.slot === 0
          ? {...pad, assetId: assigned.get(0)!}
          : pad),
      },
    },
  };
  const {container} = render(
    <App initialState={initialState} runtimeFactory={() => fixture.session} />,
  );
  await screen.findByText("3", {selector: ".project-summary dd"});
  await act(async () => hostListener?.({
    state: "running",
    errorCode: null,
    errorDetails: {},
  }));
  await screen.findByText("Audio running");
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");

  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));
  await screen.findByRole("button", {name: "Add Sample to Pad A2"});
  const sampleInput = container.querySelector<HTMLInputElement>(".sample-file-input");
  expect(sampleInput).not.toBeNull();
  await userEvent.upload(
    sampleInput!,
    wavFile("import.wav"),
  );
  await commitLongSourceSelection();
  await screen.findByText("Asset 44444444");

  await userEvent.click(screen.getByRole("button", {name: "Pad A3 — empty"}));
  const importedPad = await screen.findByRole("button", {
    name: "Pad A2 — assigned",
  });
  expect(screen.getByRole("button", {name: "Pad A4 — assigned"})).toBeTruthy();
  importedPad.focus();
  fireEvent.keyDown(importedPad, {key: "Enter", code: "Enter", repeat: false});
  await waitFor(() => expect(triggers).toEqual([1]));
  expect(screen.getByText("Audio running")).toBeTruthy();

  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(screen.getByText("5", {selector: ".project-summary dd"})).toBeTruthy();
  expect(screen.getByText("3 / 64")).toBeTruthy();
  expect(screen.getByText("3", {selector: ".project-summary dd"})).toBeTruthy();
  expect(projectionCalls).toEqual([
    "list:3",
    "inspect:3",
    "inspect:5",
    "list:5",
  ]);
  expect(fixture.calls.filter((call) => call === "openProject")).toHaveLength(1);
  expect(fixture.calls.filter((call) => call === "reloadSnapshot")).toHaveLength(1);
});

test("uses the same accept-filtered import path and keeps selection on unsupported audio", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let importCount = 0;
  fixture.session.importAssignSample = async () => {
    importCount += 1;
    throw Object.assign(new Error("/private/opfs/source-name.wav is unsupported"), {
      code: "UNSUPPORTED_AUDIO",
    });
  };
  const {container} = render(
    <App initialState={ready} runtimeFactory={() => fixture.session} />,
  );
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A2 — empty"}));

  const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
  expect(input.accept).toBe(
    ".wav,.mp3,.m4a,.aac,.flac,audio/wav,audio/wave,audio/mpeg,audio/mp4,audio/aac,audio/flac",
  );
  fireEvent.change(input, {target: {files: []}});
  expect(importCount).toBe(0);

  const pad = screen.getByRole("button", {name: "Pad A2 — empty"});
  fireEvent.drop(pad, {
    dataTransfer: {files: [new File(["not-wav"], "private-source.mp3", {
      type: "audio/mpeg",
    })]},
  });

  await screen.findByText(/the source container is not supported/);
  expect(screen.getByText("Pad A2", {selector: ".selected-sample strong"})).toBeTruthy();
  expect(screen.queryByText("private-source.mp3")).toBeNull();
  expect(screen.queryByText("/private/opfs")).toBeNull();
  expect(importCount).toBe(0);
  await userEvent.upload(input, new File(["not-wav"], "second-private.wav", {
    type: "audio/wav",
  }));
  await waitFor(() => expect(importCount).toBe(0));
  expect(screen.getByText(/the source container is not supported/)).toBeTruthy();
  expect(screen.queryByText("second-private.wav")).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(screen.getByText("3", {selector: ".project-summary dd"})).toBeTruthy();
});

test.each(["mute", "reset", "replace"] as const)(
  "%s stops an admitted Pad before mutation without waiting for Voice projection",
  async (kind) => {
    const fixture = mutableSampleRuntimeFixture();
    const order: string[] = [];
    let triggerCount = 0;
    fixture.session.trigger = async (slot, velocity, source) => {
      triggerCount += 1;
      return {sequence: triggerCount, slot, velocity, source};
    };
    fixture.session.stopPad = async (slot) => {
      order.push(`stop:${slot}`);
      return true;
    };
    fixture.session.updatePad = async (request) => {
      order.push(`mute:${request.slot}`);
      fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
      fixture.revision = 4;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    fixture.session.resetPad = async (request) => {
      order.push(`reset:${request.slot}`);
      fixture.playbacks.set(request.slot, Object.freeze({
        trimStartFrame: 0,
        trimEndFrame: 8,
        triggerMode: "one_shot",
        gainMillidb: 0,
        muted: false,
      }));
      fixture.revision = 4;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    fixture.session.importAssignSample = async (_file, options) => {
      order.push(`replace:${options.slot}`);
      fixture.assigned.set(options.slot, "44444444-4444-4444-8444-444444444444");
      fixture.playbacks.set(options.slot, Object.freeze({
        trimStartFrame: 0,
        trimEndFrame: 8,
        triggerMode: "one_shot",
        gainMillidb: 0,
        muted: false,
      }));
      fixture.revision = 4;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    const {container} = render(
      <App initialState={ready} runtimeFactory={() => fixture.session} />,
    );
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await screen.findByText("Asset 33333333");
    fireEvent.keyDown(screen.getByRole("button", {name: "Pad A1 — assigned"}), {
      key: "Enter",
      code: "Enter",
      repeat: false,
    });
    await waitFor(() => expect(triggerCount).toBe(1));

    if (kind === "mute") {
      await userEvent.click(screen.getByRole("button", {name: "Mute"}));
    } else if (kind === "reset") {
      await userEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
      await userEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
    } else {
      await userEvent.click(screen.getByRole("button", {name: "Replace Sample"}));
      const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
      await userEvent.upload(input, wavFile("replace.wav"));
      await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
      await commitLongSourceSelection();
    }

    await waitFor(() => expect(order).toEqual([`stop:0`, `${kind}:0`]));
    expect(fixture.revision).toBe(4);
  },
);

test("clears one owned Host preview when the Sample surface unmounts", async () => {
  const fixture = sampleRuntimeFixture();
  let clearCount = 0;
  fixture.session.clearSamplePreview = async (slot) => {
    expect(slot).toBe(0);
    clearCount += 1;
    return true;
  };
  const previewState: CreatorState = {
    ...ready,
    project: {
      ...ready.project,
      current: {...ready.project.current!, revision: 3},
    },
    sample: {
      ...ready.sample,
      selectedSlot: 0,
      inspect: fixture.inspect,
      auditionPlayback: fixture.inspect.playback,
      savedRevision: 3,
      runtimeRevision: 3,
    },
  };
  const view = render(
    <SampleSurface
      state={previewState}
      session={fixture.session}
      filePickIntent={{current: () => {}}}
      dispatch={vi.fn()}
    />,
  );

  view.unmount();
  await waitFor(() => expect(clearCount).toBe(1));
  expect(clearCount).toBe(1);
});

test("shows saved and stale Runtime revisions and retries Prepare explicitly", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let updateCount = 0;
  let retryCount = 0;
  fixture.session.updatePad = async (request) => {
    updateCount += 1;
    fixture.playbacks.set(request.slot, Object.freeze({...request.playback}));
    fixture.revision = 4;
    return {
      committedRevision: 4,
      runtimeRevision: 3,
      runtimePublished: false,
      snapshotError: {
        code: "COOK_FAILED",
        message: "Runtime preparation failed",
        details: {},
      },
    };
  };
  fixture.session.retryPrepare = async (patternId) => {
    retryCount += 1;
    return {
      projectId: listedSummary.projectId,
      projectRevision: 4,
      patternId,
      runtimeReady: true,
      generation: 2,
      snapshotError: null,
      runtimeRevision: 4,
    };
  };
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByText("Asset 33333333");
  expect(screen.getByText("Activate Audio to preview")).toBeTruthy();

  await userEvent.click(screen.getByRole("button", {name: "Mute"}));
  expect(await screen.findByText(
    "Saved at revision 4; Runtime is still revision 3",
  )).toBeTruthy();
  expect(updateCount).toBe(1);
  await userEvent.click(screen.getByRole("button", {name: "Retry Prepare"}));
  await waitFor(() => expect(retryCount).toBe(1));
  await waitFor(() => expect(screen.queryByText(
    "Saved at revision 4; Runtime is still revision 3",
  )).toBeNull());
});

test("gates Project actions while the Runtime is booting", async () => {
  let finishStart: ((started: boolean) => void) | undefined;
  const start = new Promise<boolean>((resolve) => { finishStart = resolve; });
  const fixture = runtimeFixture({start: () => start});
  render(<App runtimeFactory={() => fixture.session} />);

  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("button", {name: "Import .lmdj"}).hasAttribute("disabled"))
    .toBe(true);

  finishStart?.(true);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(false);
  expect(screen.getByRole("button", {name: "Import .lmdj"}).hasAttribute("disabled"))
    .toBe(false);
});

test("Open local switches Projects through one serialized visible selection", async () => {
  const secondSummary: LocalProjectSummary = {
    ...listedSummary,
    projectId: "22222222-2222-4222-8222-222222222222",
    patternId: "33333333-3333-4333-8333-333333333333",
    revision: 7,
    bpm: 128,
  };
  let opened = listedSummary;
  let secondOpenCount = 0;
  let finishSecondOpen: (() => void) | undefined;
  const secondOpen = new Promise<void>((resolve) => { finishSecondOpen = resolve; });
  const inspection = () => ({
    project_revision: opened.revision,
    project: {
      contract: "lmdj.project.v3",
      project_id: opened.projectId,
      revision: opened.revision,
      bpm: opened.bpm,
      assets: {"44444444-4444-4444-8444-444444444444": {artifact: {}}},
      banks: Array.from({length: 4}, (_, bank) => ({
        bank,
        pads: Array.from({length: 16}, (_, pad) => ({
          pad,
          asset_id: bank === 0 && pad === 0
            ? "44444444-4444-4444-8444-444444444444"
            : null,
        })),
      })),
      patterns: {[opened.patternId]: {bars: 1, events: []}},
      sequence_settings: {quantize_enabled: true, swing_percent: 50},
    },
  });
  const fixture = runtimeFixture({
    listLocalProjects: async () => [listedSummary, secondSummary],
    openProject: async (projectId) => {
      if (projectId === secondSummary.projectId) {
        secondOpenCount += 1;
        await secondOpen;
        opened = secondSummary;
      } else {
        opened = listedSummary;
      }
      return {};
    },
    inspectProject: async () => inspection(),
  });
  render(<App runtimeFactory={() => fixture.session} />);

  await userEvent.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  await screen.findByRole("heading", {name: "Project 11111111"});
  await userEvent.click(screen.getByRole("button", {name: "Open local"}));
  const openSecond = await screen.findByRole("button", {
    name: "Open Project 22222222",
  });
  fireEvent.click(openSecond);
  fireEvent.click(openSecond);

  expect(secondOpenCount).toBe(1);
  expect(screen.getByText("11111111")).toBeTruthy();
  finishSecondOpen?.();
  await screen.findByRole("heading", {name: "Project 22222222"});
});

test("disables Project actions while an import owns the action slot", async () => {
  let finishImport: ((summary: LocalProjectSummary) => void) | undefined;
  const pendingImport = new Promise<LocalProjectSummary>((resolve) => {
    finishImport = resolve;
  });
  const fixture = runtimeFixture({importProject: async () => pendingImport});
  const {container} = render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});

  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await userEvent.upload(input!, new File(["bundle"], "pending.lmdj"));
  await screen.findByText("importing");
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("button", {name: "Import .lmdj"}).hasAttribute("disabled"))
    .toBe(true);

  finishImport?.(listedSummary);
  await screen.findByRole("heading", {name: "Project 11111111"});
});

test("lists, opens, and imports through the injected Runtime Session", async () => {
  const user = userEvent.setup();
  const fixture = runtimeFixture();
  const {container} = render(
    <App runtimeFactory={() => fixture.session} />,
  );
  const open = await screen.findByRole("button", {
    name: "Open Project 11111111",
  });
  expect(screen.getByText("Revision 3")).toBeTruthy();
  expect(screen.getByText("120 BPM")).toBeTruthy();
  expect(screen.getByText("1 assigned Pad")).toBeTruthy();
  expect(screen.getByText("1 Asset")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Sample"}));
  expect(fixture.calls).toEqual(["start", "listLocalProjects"]);
  await user.click(screen.getByRole("button", {name: "Project"}));
  await user.click(screen.getByRole("button", {name: "Open Project 11111111"}));
  await screen.findByRole("heading", {name: "Project 11111111"});
  expect(screen.getAllByText("BPM").at(-1)?.nextElementSibling?.textContent)
    .toBe("120");
  expect(fixture.calls).toEqual([
    "start",
    "listLocalProjects",
    "openProject",
    "inspectProject",
    "reloadSnapshot",
  ]);

  await user.click(screen.getByRole("button", {name: "Import .lmdj"}));
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).not.toBeNull();
  await user.upload(input!, new File(["bundle"], "beat.lmdj", {
    type: "application/vnd.lmdj.project-bundle",
  }));
  await waitFor(() => expect(fixture.calls.filter((call) =>
    call === "reloadSnapshot")).toHaveLength(2));
  expect(screen.queryByText("beat.lmdj")).toBeNull();
});

test("presents Project busy with an explicit retry", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  const fixture = runtimeFixture({
    listLocalProjects: async () => {
      attempts += 1;
      if (attempts === 1) {
        throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
      }
      return [];
    },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  expect((await screen.findByRole("alert")).textContent)
    .toContain("The local Project is busy in another tab or process.");
  await user.click(screen.getByRole("button", {name: "Retry project"}));
  await screen.findByText("No local Project is open.");
  expect(attempts).toBe(2);
});

test("retries a busy Project open only after the visible Retry action", async () => {
  const user = userEvent.setup();
  let openAttempts = 0;
  const fixture = runtimeFixture({
    openProject: async () => {
      openAttempts += 1;
      if (openAttempts === 1) {
        throw Object.assign(new Error("busy"), {code: "PROJECT_BUSY"});
      }
      return {};
    },
  });
  render(<App runtimeFactory={() => fixture.session} />);

  await user.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));
  expect((await screen.findByRole("alert")).textContent)
    .toContain("The local Project is busy in another tab or process.");
  expect(openAttempts).toBe(1);

  await user.click(screen.getByRole("button", {name: "Retry project"}));
  await screen.findByRole("heading", {name: "Project 11111111"});
  expect(fixture.calls.filter((call) => call === "listLocalProjects"))
    .toHaveLength(1);
  expect(openAttempts).toBe(2);
});

test.each([
  ["INVALID_PROJECT", {}, "The Project Bundle is invalid."],
  ["DUPLICATE_ID", {},
    "The import was refused because the local copy of this Project has newer changes. Nothing was lost."],
  ["WEB_RUNTIME_RESOURCE_LIMIT", {
    resource: "ingest_decoded_frames", observed: 43200001, limit: 43200000,
  }, "ingest_decoded_frames: observed 43200001, limit 43200000."],
  ["IO_ERROR", {storage_condition: "quota_exceeded"},
    "Storage condition: quota_exceeded."],
  ["HOST_PROTOCOL_MISMATCH", {},
    "Creator and Runtime could not verify a compatible protocol."],
  ["INTERNAL_ERROR", {}, "Creator encountered an internal failure."],
  ["HOST_RESTART_REQUIRED", {terminal_state: "restart-required"},
    "Runtime must be restarted before continuing."],
] as const)("presents a safe typed %s import failure without exposing private detail", async (
  code,
  details,
  visible,
) => {
  const user = userEvent.setup();
  const fixture = runtimeFixture({
    importProject: async () => {
      throw Object.assign(new Error("/Users/private/private-name.lmdj"), {
        code,
        details,
      });
    },
  });
  const {container} = render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await user.upload(input!, new File(["bundle"], "private-name.lmdj"));

  expect((await screen.findByRole("alert")).textContent).toContain(visible);
  expect(screen.getByRole("alert").textContent).not.toContain("/Users/private");
  expect(screen.queryByText("private-name.lmdj")).toBeNull();
  if (code === "HOST_RESTART_REQUIRED") {
    expect(screen.getByTestId("creator-phase").textContent).toBe("restart-required");
    expect(screen.getByRole("button", {name: "Retry runtime"})).toBeTruthy();
  }
});

test("presents DUPLICATE_ID as a recoverable conflict, not as Creator unavailable", async () => {
  const user = userEvent.setup();
  const fixture = runtimeFixture({
    importProject: async () => {
      throw Object.assign(new Error("identifier already exists"), {
        code: "DUPLICATE_ID",
        details: {},
      });
    },
  });
  const {container} = render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await user.upload(input!, new File(["bundle"], "diverged.lmdj"));

  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("Project already on this device");
  expect(alert.textContent).toContain(
    "The import was refused because the local copy of this Project has newer changes. Nothing was lost.",
  );
  expect(alert.textContent).not.toContain("Creator unavailable");
  expect(screen.getByRole("button", {name: "Open local Project"})).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Retry project"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Retry runtime"})).toBeNull();
});

test("recovers from DUPLICATE_ID to the local Projects list without a reload", async () => {
  const user = userEvent.setup();
  let importAttempts = 0;
  const fixture = runtimeFixture({
    importProject: async () => {
      importAttempts += 1;
      throw Object.assign(new Error("identifier already exists"), {
        code: "DUPLICATE_ID",
        details: {},
      });
    },
  });
  const {container} = render(<App runtimeFactory={() => fixture.session} />);
  await screen.findByRole("button", {name: "Open Project 11111111"});
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  await user.upload(input!, new File(["bundle"], "diverged.lmdj"));
  await screen.findByRole("alert");
  const listingsBefore = fixture.calls.filter(
    (call) => call === "listLocalProjects",
  ).length;

  await user.click(screen.getByRole("button", {name: "Open local Project"}));

  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  expect(screen.getByRole("heading", {name: "Local Projects"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Open Project 11111111"}))
    .toBeTruthy();
  expect(fixture.calls.filter((call) => call === "listLocalProjects").length)
    .toBeGreaterThan(listingsBefore);
  expect(importAttempts).toBe(1);
});

test("opts into the hardware shell with a read-only overview and returns to the workspace", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  expect(screen.queryByTestId("hardware-console")).toBeNull();
  expect(screen.getByRole("heading", {name: "Project 11111111"})).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Hardware layout"}));

  expect(screen.getByRole("complementary", {name: "Physical controls"})).toBeTruthy();
  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(display).queryAllByRole("link")).toHaveLength(0);
  expect(within(display).queryAllByRole("textbox")).toHaveLength(0);
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
  expect(screen.getByRole("region", {name: "Pad matrix"})).toBeTruthy();
  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).getByRole("button", {name: "Existing workspace"})).toBeTruthy();
  expect(within(touch).getByRole("button", {name: "Activate audio"})).toBeTruthy();
  expect(within(screen.getByRole("region", {name: "Pad matrix"}))
    .getByRole("button", {name: "Pad A1 — empty — Key Q"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Project"}).getAttribute("aria-current"))
    .toBe("page");
  expect(screen.getByText("Project 11111111")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Sample"}));
  expect(screen.getByRole("heading", {name: "Sample editor"})).toBeTruthy();
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Project"}));

  await user.click(screen.getByRole("button", {name: "Existing workspace"}));
  expect(screen.queryByTestId("hardware-console")).toBeNull();
  expect(screen.getByRole("button", {name: "Hardware layout"})).toBeTruthy();
  expect(screen.getByRole("heading", {name: "Project 11111111"})).toBeTruthy();
});

test("keeps pad identity and mounts Project Sample Sequence in the hardware touch screen", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);
  await user.click(screen.getByRole("button", {name: "Hardware layout"}));

  const padMatrix = () => screen.getByRole("region", {name: "Pad matrix"});
  const touch = () => screen.getByRole("region", {name: "Touch workspace"});
  const padA1 = () => within(padMatrix()).getByRole("button", {
    name: "Pad A1 — empty — Key Q",
  });
  expect(padA1()).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();
  expect(within(touch()).getByRole("heading", {name: "Project 11111111"})).toBeTruthy();

  await user.click(screen.getByRole("button", {name: "Sample"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("SAMPLE");
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getByRole("heading", {name: "Sample editor"})).toBeTruthy();

  await user.click(screen.getByRole("button", {name: "Sequence"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("SEQUENCE");
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getByRole("heading", {name: "Sequence"})).toBeTruthy();
  expect(within(touch()).getByLabelText("Pattern")).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();

  await user.click(screen.getByRole("button", {name: "Perform"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("PERFORM");
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getByRole("heading", {name: "Perform"})).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();
  expect(screen.getByTestId("hardware-console")).toBeTruthy();

  await user.click(screen.getByRole("button", {name: "Project"}));
  expect(padA1()).toBeTruthy();
});
