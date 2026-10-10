import {IDBFactory, IDBObjectStore} from "fake-indexeddb";
import {readMonitorVolumePreference, writeMonitorVolumePreference} from "../src/state/monitor_volume_preference";
import {readFileSync} from "node:fs";

import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterAll, beforeAll, expect, test, vi} from "vitest";

import type {
  PatternTransportRequest,
  PatternTransportStatus,
  PatternTransportTicket,
} from "@lmdj/web-runtime-platform/runtime_types";

import {App} from "../src/app";
import {encodePcm16Wav} from "../src/capture/wav_encoder";
import {SampleSurface} from "../src/components/sample_surface";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import type {
  CreatorRuntimeSession,
  CreatorSequenceRuntimeSession,
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

function selectSamplePage(name: "Trim" | "Playback" | "Tone / EQ" | "Pad") {
  const button = within(screen.getByRole("navigation", {name: "Sample pages"}))
    .getByRole("button", {name});
  if (button.getAttribute("aria-current") !== "page") fireEvent.click(button);
  expect(button.getAttribute("aria-current")).toBe("page");
}

// The technical identity moved to Pad > Sample details. Preserve the complete
// identity assertion and return to the original editor page before its journey.
async function expectSelectedAsset(assetId: string): Promise<void> {
  const pages = screen.getByRole("navigation", {name: "Sample pages"});
  const previous = pages.querySelector('[aria-current="page"]')!.textContent as
    "Trim" | "Playback" | "Tone / EQ" | "Pad";
  selectSamplePage("Pad");
  const summary = screen.getByText("Sample details", {selector: "summary"});
  const details = summary.parentElement as HTMLDetailsElement;
  if (!details.open) await userEvent.click(summary);
  await within(details).findByText(assetId, {exact: true});
  selectSamplePage(previous);
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
      pads: Array.from({length: 64}, (_, slot) => ({slot, assetId: null, category: null, colourOverride: null, colour: null})),
      patterns: [{
        patternId: "22222222-2222-4222-8222-222222222222",
        bars: 1,
        events: [],
      }],
      patternSlots: Object.freeze(Array<string | null>(16).fill(null)),
      sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
    },
  },
  runtime: {phase: "ready", errorCode: null},
};

// The hardware layout is the default, so Project truth is read off the upper
// screen's facts rather than the old workspace summary.
const revisionCell = () => screen.getByText("Rev").nextElementSibling;
const transportPhase = () =>
  document.querySelector(".overview-phase")?.textContent?.split("/").pop()?.trim();

test("enables keyboard-reachable Sample while preserving the other mode states", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  const projectMode = screen.getByRole("button", {name: "Project"});
  expect(projectMode.hasAttribute("disabled")).toBe(false);
  const sampleMode = screen.getByRole("button", {name: "Sample"});
  expect(sampleMode.hasAttribute("disabled")).toBe(false);
  expect(sampleMode.tabIndex).toBe(0);
  expect(screen.queryByRole("button", {name: "Slice"})).toBeNull();
  const sequenceMode = screen.getByRole("button", {
    name: "Sequence — open a playable Project first",
  });
  expect(sequenceMode.hasAttribute("disabled")).toBe(true);
  // The Perform key keeps the looser hardware gate: a ready Project reaches
  // a touch workspace that names what is missing, rather than a disabled key.
  const performMode = screen.getByRole("button", {name: "Perform"});
  expect(performMode.hasAttribute("disabled")).toBe(false);

  expect(screen.getByText("Key").nextElementSibling?.textContent).toBe("—");
  expect(screen.queryByText(/untitled/i)).toBeNull();
  expect(screen.queryByText(/beat\.lmdj/i)).toBeNull();
  const keys = [
    "Q", "W", "E", "R", "T", "Y", "U", "I",
    "A", "S", "D", "F", "G", "H", "J", "K",
  ];
  for (const [index, key] of keys.entries()) {
    expect(screen.getByRole("button", {
      name: `Pad A${String(index + 1).padStart(2, "0")} — empty — Key ${key}`,
    })).toBeTruthy();
  }
  expect(Array.from(document.querySelectorAll(".pad kbd"), (key) => key.textContent))
    .toEqual(["G", "H", "J", "K", "A", "S", "D", "F",
      "T", "Y", "U", "I", "Q", "W", "E", "R"]);

  expect(screen.queryByRole("button", {name: "Activate audio"})).toBeNull();
  // The brand mark is the System entry and the rail's first stop.
  await user.tab();
  expect(document.activeElement).toBe(screen.getByRole("button", {name: "System"}));
  await user.tab();
  expect(document.activeElement).toBe(projectMode);
  await user.tab();
  expect(document.activeElement).toBe(sampleMode);
  await user.keyboard("{Enter}");
  expect(sampleMode.getAttribute("aria-current")).toBe("page");
  expect(projectMode.hasAttribute("aria-current")).toBe(false);
  expect(screen.getByRole("heading", {name: "Sample editor"})).toBeTruthy();
  expect(screen.getAllByRole("button", {
    name: /^Pad A(?:0[1-9]|1[0-6]) — empty — Key [QWERTYUIASDFGHJK]$/,
  })).toHaveLength(16);
  expect(within(screen.getByRole("complementary", {name: "Physical controls"}))
    .getByRole("button", {name: "Bank A"})).toBeTruthy();

  await user.click(projectMode);
  expect(projectMode.getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("button", {name: "Open local"}).hasAttribute("disabled"))
    .toBe(true);
  expect(screen.getByRole("heading", {name: "Project 11111111"})).toBeTruthy();
});

test("keeps Sample editing in touch and one Bank row and Pad matrix on the rail", async () => {
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
          reverse: false,
          pitchCents: 0,
          pan: 0,
          loopMode: "forward" as const,
          loopStartFrame: null,
          loopCrossfadeFrames: 0,
          attackMs: 0,
          releaseMs: 0,
          tone: 0,
          eq: {low: null, mid: null, high: null},
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

  const selectedPad = document.querySelector(".selected-sample")!;
  const waveform = screen.getByRole("region", {name: "Pad A01 waveform editor"});
  const pads = screen.getByRole("region", {name: "Pad matrix"});
  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).queryByLabelText("Playable Pads")).toBeNull();
  expect(within(touch).queryByRole("button", {name: /^Bank [ABCD]$/})).toBeNull();
  expect(screen.getAllByLabelText("Playable Pads")).toHaveLength(1);
  const rail = screen.getByRole("complementary", {name: "Physical controls"});
  for (const bank of ["A", "B", "C", "D"]) {
    expect(screen.getAllByRole("button", {name: `Bank ${bank}`})).toHaveLength(1);
    expect(within(rail).getByRole("button", {name: `Bank ${bank}`})).toBeTruthy();
  }
  expect(selectedPad.compareDocumentPosition(waveform) & Node.DOCUMENT_POSITION_FOLLOWING)
    .not.toBe(0);
  expect(touch.contains(selectedPad)).toBe(true);
  expect(selectedPad.textContent).toBe("Pad A01");
  expect(document.querySelector(".overview-context")?.textContent).toBe("SAMPLE / PAD A01");
  expect(within(touch).queryByText(/frames$/)).toBeNull();
  expect(touch.contains(waveform)).toBe(true);
  expect(screen.queryByRole("region", {name: "Pad A01 Sample controls"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Edit Pad A01"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Replace Sample"})).toBeNull();
  const pages = screen.getByRole("navigation", {name: "Sample pages"});
  await userEvent.click(within(pages).getByRole("button", {name: "Playback"}));
  expect(screen.queryByRole("region", {name: "Pad A01 waveform editor"})).toBeNull();
  expect(within(touch).getByRole("slider", {name: "Pad A01 Volume"})).toBeTruthy();
  expect(screen.queryByRole("slider", {name: "Pad A01 Tone"})).toBeNull();
  await userEvent.click(within(pages).getByRole("button", {name: "Tone / EQ"}));
  expect(within(touch).getByRole("slider", {name: "Pad A01 Tone"})).toBeTruthy();
  expect(screen.queryByRole("slider", {name: "Pad A01 Volume"})).toBeNull();
  await userEvent.click(within(pages).getByRole("button", {name: "Pad"}));
  await userEvent.click(screen.getByText("Sample details", {selector: "summary"}));
  const details = screen.getByText("Sample details", {selector: "summary"}).parentElement!;
  expect(within(details).getByText(sampleReady.sample.inspect!.assetId!)).toBeTruthy();
  expect(within(details).getByText("48 kHz · Mono · 8 frames")).toBeTruthy();
  expect(within(details).getByText("Revision").nextElementSibling?.textContent).toBe("4");
  expect(screen.getByRole("button", {name: "Replace Sample"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Record Sample"})).toBeTruthy();
  expect(within(screen.getByRole("region", {name: "Pad A01 management"}))
    .getByRole("button", {name: "Reset Pad to Defaults"})).toBeTruthy();
  expect(screen.getByText("Tap a Pad to preview")).toBeTruthy();
  const visiblePads = screen.getAllByRole("button", {
    name: /^Pad A(?:0[1-9]|1[0-6]) — (?:assigned|empty) — Key [QWERTYUIASDFGHJK]$/,
  });
  expect(visiblePads).toHaveLength(16);
  for (const pad of visiblePads) {
    expect(pads.contains(pad)).toBe(true);
  }
});

test("advances the selected Sample playhead on the render clock and cancels it at a terminal edge", () => {
  let animationFrame: FrameRequestCallback | undefined;
  const requestAnimationFrame = vi.spyOn(window, "requestAnimationFrame")
    .mockImplementation((callback) => {
      animationFrame = callback;
      return 71;
    });
  const cancelAnimationFrame = vi.spyOn(window, "cancelAnimationFrame")
    .mockImplementation(() => {});
  const now = vi.spyOn(performance, "now").mockReturnValue(1_000);
  const inspect = {
    projectRevision: 4,
    slot: 0,
    assetId: "33333333-3333-4333-8333-333333333333",
    playback: {
      trimStartFrame: 0,
      trimEndFrame: 48_000,
      triggerMode: "one_shot" as const,
      gainMillidb: 0,
      muted: false,
      reverse: false,
      pitchCents: 0,
      pan: 0,
      loopMode: "forward" as const,
      loopStartFrame: null,
      loopCrossfadeFrames: 0,
      attackMs: 0,
      releaseMs: 0,
      tone: 0,
      eq: {low: null, mid: null, high: null},
    },
    metadata: {sampleRate: 48_000 as const, channels: 1 as const, sourceFrames: 48_000},
    waveformCacheIdentity: `${"a".repeat(64)}/1/max-abs-mirror/94`,
  };
  const playing: CreatorState = {
    ...ready,
    audio: {phase: "running"},
    sample: {
      ...ready.sample,
      selectedSlot: 0,
      inspect,
      waveform: {
        metadata: inspect.metadata,
        algorithmVersion: 1,
        buckets: [{startFrame: 0, endFrame: 48_000, peakMagnitude: 16_384}],
        projectRevision: 4,
      },
      viewport: {sourceFrames: 48_000, startFrame: 0, endFrame: 48_000},
      voices: [{
        sequence: 1,
        slot: 0,
        state: "started",
        runtimeFrame: 128,
        sourceFrame: 0,
        sampleRate: 48_000,
        trimStartFrame: 0,
        trimEndFrame: 48_000,
      }],
      playhead: {
        sequence: 1,
        slot: 0,
        runtimeFrame: 128,
        observedAtMilliseconds: 1_000,
        sourceFrame: 0,
        sampleRate: 48_000,
        trimStartFrame: 0,
        trimEndFrame: 48_000,
        triggerMode: "one_shot",
        reverse: false,
        pitchCents: 0,
        loopMode: "forward",
        loopStartFrame: null,
        loopCrossfadeFrames: 0,
      },
      savedRevision: 4,
      runtimeRevision: 4,
    },
  };

  try {
    const view = render(
      <SampleSurface
        state={playing}
        filePickIntent={{current: () => {}}}
        dispatch={vi.fn()}
      />,
    );
    expect(view.container.querySelector("line[data-playhead]")?.getAttribute("x1"))
      .toBe("0");
    act(() => animationFrame?.(1_500));
    expect(view.container.querySelector("line[data-playhead]")?.getAttribute("x1"))
      .toBe("200");

    view.rerender(
      <SampleSurface
        state={{...playing, sample: {...playing.sample, voices: [], playhead: null}}}
        filePickIntent={{current: () => {}}}
        dispatch={vi.fn()}
      />,
    );
    expect(view.container.querySelector("line[data-playhead]")).toBeNull();
    expect(cancelAnimationFrame).toHaveBeenCalledWith(71);
  } finally {
    requestAnimationFrame.mockRestore();
    cancelAnimationFrame.mockRestore();
    now.mockRestore();
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
  const pad = screen.getByRole("button", {name: "Pad A01 — assigned — Key Q"});
  pad.focus();
  const sourceName = `${"<img src=x onerror=private>".repeat(8)}.wav`;
  fireEvent.drop(pad, {
    dataTransfer: {files: [wavFile(sourceName)]},
  });

  const dialog = screen.getByRole("dialog", {name: "Replace Pad A01?"});
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
  expect(screen.queryByRole("dialog", {name: "Replace Pad A01?"})).toBeNull();
  expect(document.activeElement).toBe(pad);
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(revisionCell()?.textContent).toBe("4");
});

test("Record on an assigned Pad confirms the replacement before the panel opens", async () => {
  const fixture = mutableSampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

  // S8-D12: recording onto an assigned Pad is a replacement, so the existing
  // confirmation runs before the microphone is ever requested (S8B-D2).
  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  expect(screen.queryByRole("dialog", {name: "Pad A01 Pad Capture"})).toBeNull();
  const dialog = screen.getByRole("dialog", {name: "Replace Pad A01?"});
  expect(dialog.textContent).toContain(
    "Replacing the Sample resets Start, End, trigger, Loop, Volume, and Mute.",
  );

  await userEvent.click(screen.getByRole("button", {name: "Cancel replace"}));
  expect(screen.queryByRole("dialog", {name: "Pad A01 Pad Capture"})).toBeNull();

  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
  expect(screen.getByRole("dialog", {name: "Pad A01 Pad Capture"})).toBeTruthy();
});

test("Record on an empty Pad opens the capture panel with no replacement prompt", async () => {
  const fixture = mutableSampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));

  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  expect(screen.queryByRole("dialog", {name: "Replace Pad A02?"})).toBeNull();
  expect(screen.getByRole("dialog", {name: "Pad A02 Pad Capture"})).toBeTruthy();

  await userEvent.click(screen.getByRole("button", {name: "Close"}));
  expect(screen.queryByRole("dialog", {name: "Pad A02 Pad Capture"})).toBeNull();
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
  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));
  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Record Sample"}));
  const dialog = screen.getByRole("dialog", {name: "Pad A02 Pad Capture"});

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
  expect(screen.getByRole("dialog", {name: "Pad A02 Pad Capture"})).toBe(dialog);
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
    duplicateProject: async () => { throw new Error("duplicate is not expected"); },
    createProject: async () => { calls.push("createProject"); return {}; },
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
              category: null, colour_override: null, colour: null,
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

// These lifecycle tests use synthetic events and an already-running fixture.
// Trusted browser activation is covered by the packaged first-gesture journey.
function setRunningAudioFixture(session: CreatorRuntimeSession) {
  const diagnostics = session.diagnostics;
  session.diagnostics = () => ({...diagnostics(), state: "running"});
}

// Component-only Host state seam. Publishing running after Project open keeps
// the visual audio state aligned with diagnostics; this is not trusted browser
// activation or physical audio evidence.
function controlledSampleAudio(session: CreatorRuntimeSession) {
  let publish!: (state: RuntimeHostState) => void;
  session.subscribeHostState = (listener) => { publish = listener; return () => {}; };
  return () => act(() => {
    setRunningAudioFixture(session);
    publish({state: "running", errorCode: null, errorDetails: {}});
  });
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
      reverse: false,
      pitchCents: 0,
      pan: 0,
      loopMode: "forward" as const,
      loopStartFrame: null,
      loopCrossfadeFrames: 0,
      attackMs: 0,
      releaseMs: 0,
      tone: 0,
      eq: {low: null, mid: null, high: null},
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
    deletePad: async () => ({
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

// Real App/RuntimeProvider/PadCapture/Sources/CaptureController callbacks;
// only browser devices and the Facade session are controlled here. This
// proves replacement ownership, not trusted input or microphone hearing.
test.each([
  ["microphone", "save"], ["microphone", "discard"],
  ["master", "save"], ["master", "discard"],
  ["microphone", "occupied-target refusal"],
])("Runtime replacement retains the original %s Pad take for explicit %s", async (source, resolution) => {
  const closed = deferred<void>();
  const acquired = deferred<void>();
  const fixture = mutableSampleRuntimeFixture();
  // An already-running controlled Runtime lets synthetic input exercise the
  // master resource lifecycle without claiming trusted browser activation.
  setRunningAudioFixture(fixture.session);
  let restart!: (state: RuntimeHostState) => void;
  fixture.session.subscribeHostState = listener => {restart = listener; return () => {};};
  fixture.session.close = vi.fn(async () => true);
  const originalImport = vi.fn(fixture.session.importAssignSample);
  fixture.session.importAssignSample = originalImport;
  const stopMaster = vi.fn(() => closed.promise);
  const startMaster = vi.fn(async (callbacks: {onBatch(channels: Float32Array[]): void}) => {
    callbacks.onBatch([new Float32Array([0, .25, .1]), new Float32Array([0, -.25, -.1])]);
    await acquired.promise;
    return {stop: stopMaster};
  });
  if (source === "master") {
    Object.assign(fixture.session, performanceSessionStubs([]).stubs, {
      startPerformanceMasterCapture: startMaster,
    });
  }
  const importTake = vi.fn<CreatorSampleRuntimeSession["importAssignSample"]>(async (_file, options) => {
    fixture.assigned.set(options.slot, "44444444-4444-4444-8444-444444444444");
    fixture.revision++;
    return {committedRevision: fixture.revision, runtimeRevision: fixture.revision,
      runtimePublished: true, snapshotError: null};
  });
  const successor = {...fixture.session, importAssignSample: importTake};
  const nodes: Array<{port: {onmessage: ((event: {data: unknown}) => void) | null}}> = [];
  const tracks: Array<{stop: ReturnType<typeof vi.fn>}> = [];
  let contexts = 0;
  vi.stubGlobal("navigator", {
    permissions: {query: async () => ({state: "granted"})},
    mediaDevices: {getUserMedia: async () => {
      const track = {stop: vi.fn(), addEventListener() {}, removeEventListener() {}};
      tracks.push(track); return {getTracks: () => [track], getAudioTracks: () => [track]};
    }},
  });
  vi.stubGlobal("AudioContext", class {
    readonly first = ++contexts === 1;
    audioWorklet = {addModule: async () => {}};
    resume() {return Promise.resolve();}
    close() {return this.first ? closed.promise : Promise.resolve();}
    createMediaStreamSource() {return {connect() {}, disconnect() {}};}
  });
  vi.stubGlobal("AudioWorkletNode", class {
    port = {onmessage: null};
    constructor() {nodes.push(this);}
    disconnect() {}
  });
  vi.stubGlobal("localStorage", {getItem: () => source === "master" ? "master" : null,
    setItem() {}, removeItem() {}});
  let creations = 0;
  const sessions = [fixture.session, successor];
  const rendered = render(<App initialState={ready} runtimeFactory={() => sessions[creations++]!} />);
  try {
    const pad = await screen.findByRole("button", {name: /^Pad A02 — empty/});
    await flushAsyncTurns();
    await waitFor(() => expect((pad as HTMLButtonElement).disabled).toBe(false));
    // The source is a System setting: no Pad recording row sits in the touch
    // area until a take starts, and System shows the remembered source.
    expect(screen.queryByRole("region", {name: "Pad recording"})).toBeNull();
    fireEvent.click(screen.getByRole("button", {name: "System"}));
    expect((screen.getByRole("combobox", {name: "Pad recording source"}) as HTMLSelectElement)
      .value).toBe(source);
    fireEvent.click(screen.getByRole("button", {name: "Back to music"}));
    fireEvent.mouseDown(pad, {button: 0});
    const recording = screen.getByRole("region", {name: "Pad recording"});
    await waitFor(() => expect(recording.textContent).toContain(
      `${source === "master" ? "starting" : "recording"} · Pad A02`));
    if (source === "microphone") {
      act(() => nodes[0]!.port.onmessage?.({data: {channels: [new Float32Array([0, .25, .1])], peak: .25}}));
    } else {
      await waitFor(() => expect(startMaster).toHaveBeenCalledOnce());
    }
    act(() => restart({state: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {}}));
    await flushAsyncTurns();
    if (source === "master") {
      // Master acquisition is not abortable: replacement must join the late
      // handle, then its real stop promise, before retiring the Runtime.
      expect(creations).toBe(1); expect(stopMaster).not.toHaveBeenCalled();
      expect(fixture.session.close).not.toHaveBeenCalled();
      await act(async () => acquired.resolve());
      await waitFor(() => expect(stopMaster).toHaveBeenCalledOnce());
    } else {
      await waitFor(() => expect(tracks[0]!.stop).toHaveBeenCalledOnce());
    }
    // The old Context.close is pending: neither close nor factory can run.
    expect(fixture.session.close).not.toHaveBeenCalled();
    expect(creations).toBe(1);
    expect(recording.textContent).toContain("stopping · Pad A02");
    expect(importTake).not.toHaveBeenCalled();
    await act(async () => closed.resolve());
    await waitFor(() => expect(creations).toBe(2));
    await screen.findByRole("button", {name: /^Pad A02 — empty/});
    await flushAsyncTurns();
    expect(recording.textContent).toContain("review · Pad A02");
    // A different Pad cannot steal the unresolved take or open a source.
    fireEvent.mouseDown(screen.getByRole("button", {name: /^Pad A03 — empty/}), {button: 0});
    await flushAsyncTurns();
    expect(source === "master" ? stopMaster.mock.calls.length : contexts).toBe(1);
    expect(recording.textContent).toContain("review · Pad A02");
    fireEvent.click(screen.getByRole("button", {name: "System"}));
    expect(within(recording).getByRole("button", {name: "Save Pad recording"})).toBeTruthy();
    expect(within(recording).getByRole("button", {name: "Discard Pad recording"})).toBeTruthy();
    if (resolution === "occupied-target refusal") {
      // A concurrent authoring result never becomes an implicit replacement.
      fixture.assigned.set(1, "55555555-5555-4555-8555-555555555555");
      await userEvent.click(within(recording).getByRole("button", {name: "Save Pad recording"}));
      await within(recording).findByText("This Pad now contains a sound. Keep or discard this take.");
      expect(importTake).not.toHaveBeenCalled();
      expect(recording.textContent).toContain("review · Pad A02");
      await userEvent.click(within(recording).getByRole("button", {name: "Discard Pad recording"}));
      expect(fixture.assigned.get(1)).toBe("55555555-5555-4555-8555-555555555555");
    } else if (resolution === "save") {
      await userEvent.click(within(recording).getByRole("button", {name: "Save Pad recording"}));
      await waitFor(() => expect(importTake).toHaveBeenCalledOnce());
      expect(importTake.mock.calls[0]![1]).toMatchObject({slot: 1, expectedRevision: 3});
      const file = importTake.mock.calls[0]![0];
      const bytes = await new Promise<ArrayBuffer>((resolve, reject) => {
        const reader = new FileReader(); reader.onload = () => resolve(reader.result as ArrayBuffer);
        reader.onerror = reject; reader.readAsArrayBuffer(file);
      });
      expect(bytes.byteLength).toBe(source === "master" ? 52 : 48);
      expect(new DataView(bytes).getInt16(44, true)).toBe(8192);
      expect(new DataView(bytes).getInt16(source === "master" ? 48 : 46, true)).toBe(3277);
      if (source === "master") expect(new DataView(bytes).getInt16(46, true)).toBe(-8192);
      expect(fixture.assigned.get(1)).toBe("44444444-4444-4444-8444-444444444444");
    } else {
      await userEvent.click(within(recording).getByRole("button", {name: "Discard Pad recording"}));
      expect(importTake).not.toHaveBeenCalled(); expect(fixture.assigned.has(1)).toBe(false);
    }
    // An idle Pad recording with nothing to report leaves the touch area.
    await waitFor(() =>
      expect(screen.queryByRole("region", {name: "Pad recording"})).toBeNull());
    expect(originalImport).not.toHaveBeenCalled();
    // System never hid the decision; return before starting the next take.
    fireEvent.click(screen.getByRole("button", {name: "Back to music"}));
    // After the deliberate resolution the successor can own a new take.
    fireEvent.mouseDown(screen.getByRole("button", {name: /^Pad A03 — empty/}), {button: 0});
    const next = () => screen.getByRole("region", {name: "Pad recording"});
    await waitFor(() => expect(next().textContent).toContain("recording · Pad A03"));
    if (source === "microphone") expect(contexts).toBe(2);
    await flushAsyncTurns();
    expect(next().textContent).toContain("recording · Pad A03");
  } finally {
    acquired.resolve(); closed.resolve(); rendered.unmount(); await flushAsyncTurns(); vi.unstubAllGlobals();
  }
});

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
      reverse: false,
      pitchCents: 0,
      pan: 0,
      loopMode: "forward" as const,
      loopStartFrame: null,
      loopCrossfadeFrames: 0,
      attackMs: 0,
      releaseMs: 0,
      tone: 0,
      eq: {low: null, mid: null, high: null},
    })],
  ]);
  // The Pad colour fields `project.inspect` carries, as Core resolved them.
  const padColours = new Map<number, {
    category: string | null; colour_override: number | null; colour: number | null;
  }>();
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
      reverse: false,
      pitchCents: 0,
      pan: 0,
      loopMode: "forward" as const,
      loopStartFrame: null,
      loopCrossfadeFrames: 0,
      attackMs: 0,
      releaseMs: 0,
      tone: 0,
      eq: {low: null, mid: null, high: null},
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
          ...(padColours.get(bank * 16 + pad) ??
            {category: null, colour_override: null, colour: null}),
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
    padColours,
    summary,
    inspectSample,
    inspectProject,
    get revision() { return revision; },
    set revision(value: number) { revision = value; },
  };
}

async function candidatePlaybackFixture(runningAudio = false,
  configure?: (fixture: ReturnType<typeof mutableSampleRuntimeFixture>) => void) {
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
  if (runningAudio) setRunningAudioFixture(session);
  configure?.(fixture);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
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
  expect(screen.getByText("Changes saved · playback needs preparation.")).toBeTruthy();
  expect((screen.getByText("Saved at revision 4; audio is not ready.")
    .closest("details") as HTMLDetailsElement).open).toBe(false);
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
  await userEvent.click(screen.getByRole("button", {name: "Retry audio preparation"}));
  await waitFor(() => expect(fixture.prepare).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(screen.queryByRole("region", {name: "Project audio status"})).toBeNull());
  expect(fixture.adopt).toHaveBeenCalledTimes(1);
  expect(fixture.revision).toBe(4);
});

test.each(["pointer", "keyboard", "midi"])("Candidate preparation blocks %s Pad admission until successful retry", async (source) => {
  const fixture = await candidatePlaybackFixture(true);
  const midiInput = Object.assign(new EventTarget(), {type: "input", state: "connected", id: "candidate-test"});
  if (source === "midi") {
    const original = Object.getOwnPropertyDescriptor(navigator, "requestMIDIAccess");
    Object.defineProperty(navigator, "requestMIDIAccess", {configurable: true,
      value: async () => ({inputs: new Map([["candidate-test", midiInput]])})});
    try {
      await userEvent.click(screen.getByRole("button", {name: "System"}));
      await userEvent.click(screen.getByRole("button", {name: "Enable MIDI"}));
      await userEvent.click(screen.getByRole("button", {name: "Back to music"}));
    }
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
  const pending = deferred<SnapshotPublication>();
  fixture.prepare.mockImplementationOnce(() => pending.promise);
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await screen.findByText("Preparing audio at revision 4…");
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  const pad = screen.getByRole("button", {name: /^Pad A01 — assigned/});
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
  const runAudio = controlledSampleAudio(fixture.session);
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Playback");
  const volume = screen.getByRole("slider", {name: "Pad A01 Volume"});

  runAudio();
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio running");
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
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

    const selectedAfter = 1;
    if (kind === "update") {
      selectSamplePage("Playback");
      await userEvent.click(screen.getByRole("button", {name: "Mute"}));
    } else {
      selectSamplePage("Pad");
      await userEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
      await userEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
    }
    await waitFor(() => expect(operationCount).toBe(1));
    await userEvent.click(screen.getByRole("button", {
      name: `Pad A${String(selectedAfter + 1).padStart(2, "0")} — empty — Key ${"QWERTYUIASDFGHJK"[selectedAfter]}`,
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
        reverse: false,
        pitchCents: 0,
        pan: 0,
        loopMode: "forward" as const,
        loopStartFrame: null,
        loopCrossfadeFrames: 0,
        attackMs: 0,
        releaseMs: 0,
        tone: 0,
        eq: {low: null, mid: null, high: null},
      }));
    }
    fixture.revision = 4;
    await act(async () => mutation.resolve({
      committedRevision: 4,
      runtimeRevision: 4,
      runtimePublished: true,
      snapshotError: null,
    }));

    await screen.findByText(`Pad A${String(selectedAfter + 1).padStart(2, "0")}`, {
      selector: ".selected-sample strong",
    });
    await waitFor(() => expect(
      screen.getByRole("button", {name: `Add Sample to Pad A${String(selectedAfter + 1).padStart(2, "0")}`})
        .hasAttribute("disabled"),
    ).toBe(false));
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(revisionCell()?.textContent).toBe("4");
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Playback");
  await userEvent.click(screen.getByRole("button", {name: "Mute"}));

  expect((await screen.findByRole("alert")).textContent).toBe(
    "Project changed; review and try again",
  );
  expect(updateCount).toBe(1);
  expect(screen.getByRole("button", {name: "Pad A02 — assigned — Key W"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(revisionCell()?.textContent).toBe("4");
  expect(screen.getByText("Pads").nextElementSibling?.textContent).toBe("2 / 64");
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));
  const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
  await userEvent.upload(input, wavFile("interleaved.wav"));
  await commitLongSourceSelection();

  await expectSelectedAsset("44444444-4444-4444-8444-444444444444");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(screen.getByRole("button", {name: "Pad A04 — assigned — Key R"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Pad A05 — assigned — Key T"})).toBeTruthy();
  expect(screen.getByText("Audio running")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(revisionCell()?.textContent).toBe("6");
  expect(screen.getByText("Pads").nextElementSibling?.textContent).toBe("4 / 64");
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
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

    vi.useFakeTimers();
    try {
      selectSamplePage("Playback");
      fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      await flushAsyncTurns();

      expect(screen.getByText(
        "The sound was saved, but Creator could not show the latest Project.",
      )).toBeTruthy();
      expect(screen.getByText("Creator unavailable")).toBeTruthy();
      expect(screen.getByText(code === "HOST_PROTOCOL_MISMATCH"
        ? "This copy of Creator is out of date."
        : code === "HOST_RESTART_REQUIRED"
          ? "The audio engine stopped. Your Project is saved and not affected."
          : "That item is no longer in this Project."),
      ).toBeTruthy();
      expect(screen.getByText("Creator unavailable").closest("[role=alert]")?.textContent ?? "")
        .not.toContain(code);
      const pad = screen.getByRole("button", {name: "Pad A01 — empty — Key Q"});
      expect(pad.hasAttribute("disabled")).toBe(true);
      const settledReads = projectReads;
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      expect(projectReads).toBe(settledReads);
      expect(settledReads).toBeGreaterThan(0);
      expect(settledReads).toBeLessThanOrEqual(4);
      expect(screen.queryByText("Creator could not change this sound.")).toBeNull();
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
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
    selectSamplePage("Playback");
    await userEvent.click(screen.getByRole("button", {name: "Mute"}));

    selectSamplePage("Pad");
    await waitFor(() => expect(screen.getByRole("button", {
      name: "Reset Pad to Defaults",
    }).hasAttribute("disabled")).toBe(false));
    expect(fixture.mutationCount).toBe(1);
    expect(fixture.busyCount).toBe(busyFailures);
    expect(screen.queryByRole("alert")).toBeNull();
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(revisionCell()?.textContent).toBe(source === "sample" ? "5" : "4");
  },
);

test.each(["project", "sample"] as const)(
  "bounds persistent PROJECT_BUSY from $source inspection",
  async (source) => {
    const fixture = busyProjectionFixture(source, null);
    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

    vi.useFakeTimers();
    try {
      selectSamplePage("Playback");
      fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      await flushAsyncTurns();
      await act(async () => { await vi.advanceTimersByTimeAsync(5_000); });
      await flushAsyncTurns();

      expect(screen.getByText(
        "The sound was saved, but Creator could not show the latest Project.",
      )).toBeTruthy();
      expect(screen.getByText(/^The audio engine stopped/)).toBeTruthy();
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
        reverse: false,
        pitchCents: 0,
        pan: 0,
        loopMode: "forward" as const,
        loopStartFrame: null,
        loopCrossfadeFrames: 0,
        attackMs: 0,
        releaseMs: 0,
        tone: 0,
        eq: {low: null, mid: null, high: null},
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
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

    vi.useFakeTimers();
    try {
      if (kind === "update") {
        selectSamplePage("Playback");
        fireEvent.click(screen.getByRole("button", {name: "Mute"}));
      } else {
        selectSamplePage("Pad");
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
      selectSamplePage("Pad");
      expect(screen.getByRole("button", {name: "Reset Pad to Defaults"})
        .hasAttribute("disabled")).toBe(false);
      fireEvent.click(screen.getByRole("button", {name: "Project"}));
      expect(revisionCell()?.textContent).toBe("4");
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));
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
  setRunningAudioFixture(fixture.session);
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  const pad = screen.getByRole("button", {name: "Pad A01 — assigned — Key Q"});
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
      reverse: false,
      pitchCents: 0,
      pan: 0,
      loopMode: "forward" as const,
      loopStartFrame: null,
      loopCrossfadeFrames: 0,
      attackMs: 0,
      releaseMs: 0,
      tone: 0,
      eq: {low: null, mid: null, high: null},
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
              category: null, colour_override: null, colour: null,
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
  await waitFor(() => expect(revisionCell()?.textContent).toBe("3"));
  await act(async () => hostListener?.({
    state: "running",
    errorCode: null,
    errorDetails: {},
  }));
  await screen.findByText("Audio running");
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");

  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));
  await screen.findByRole("button", {name: "Add Sample to Pad A02"});
  const sampleInput = container.querySelector<HTMLInputElement>(".sample-file-input");
  expect(sampleInput).not.toBeNull();
  await userEvent.upload(
    sampleInput!,
    wavFile("import.wav"),
  );
  await commitLongSourceSelection();
  await expectSelectedAsset("44444444-4444-4444-8444-444444444444");

  await userEvent.click(screen.getByRole("button", {name: "Pad A03 — empty — Key E"}));
  const importedPad = await screen.findByRole("button", {
    name: "Pad A02 — assigned — Key W",
  });
  expect(screen.getByRole("button", {name: "Pad A04 — assigned — Key R"})).toBeTruthy();
  importedPad.focus();
  fireEvent.keyDown(importedPad, {key: "Enter", code: "Enter", repeat: false});
  await waitFor(() => expect(triggers).toEqual([1]));
  expect(screen.getByText("Audio running")).toBeTruthy();

  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(revisionCell()?.textContent).toBe("5");
  expect(screen.getByText("Pads").nextElementSibling?.textContent).toBe("3 / 64");
  expect(screen.getByText("Assets").nextElementSibling?.textContent).toBe("3");
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));

  const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
  expect(input.accept).toBe(
    ".wav,.mp3,.m4a,.aac,.flac,audio/wav,audio/wave,audio/mpeg,audio/mp4,audio/aac,audio/flac",
  );
  fireEvent.change(input, {target: {files: []}});
  expect(importCount).toBe(0);

  const pad = screen.getByRole("button", {name: "Pad A02 — empty — Key W"});
  fireEvent.drop(pad, {
    dataTransfer: {files: [new File(["not-wav"], "private-source.mp3", {
      type: "audio/mpeg",
    })]},
  });

  await screen.findByText(/This type of audio file is not supported\. Choose a WAV, MP3, M4A\/AAC or FLAC file\./, {selector: "[role=alert]"});
  // The resource token and limit stay in diagnostics, out of the alert.
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  await userEvent.click(screen.getByText(/^Developer diagnostics \(\d+\)$/));
  expect(within(screen.getByRole("region", {name: "Developer diagnostics"}))
    .getByText("Read Sample source")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Back to music"}));
  expect(screen.getByText("Pad A02", {selector: ".selected-sample strong"})).toBeTruthy();
  expect(screen.queryByText("private-source.mp3")).toBeNull();
  expect(screen.queryByText("/private/opfs")).toBeNull();
  expect(importCount).toBe(0);
  await userEvent.upload(input, new File(["not-wav"], "second-private.wav", {
    type: "audio/wav",
  }));
  await waitFor(() => expect(importCount).toBe(0));
  expect(screen.getByText(/This type of audio file is not supported\. Choose a WAV, MP3, M4A\/AAC or FLAC file\./, {selector: "[role=alert]"})).toBeTruthy();
  expect(screen.queryByText("second-private.wav")).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(revisionCell()?.textContent).toBe("3");
});

test.each(["mute", "reset", "replace", "delete"] as const)(
  "%s stops an admitted Pad before mutation without waiting for Voice projection",
  async (kind) => {
    const fixture = mutableSampleRuntimeFixture();
    const order: string[] = [];
    let triggerCount = 0;
    // A Pad can sound only while audio runs, so the Host admits the press
    // only then; the stop-first order applies to that state (#1724).
    let hostListener: ((state: RuntimeHostState) => void) | undefined;
    fixture.session.subscribeHostState = (listener) => {
      hostListener = listener;
      return () => {};
    };
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
        reverse: false,
        pitchCents: 0,
        pan: 0,
        loopMode: "forward" as const,
        loopStartFrame: null,
        loopCrossfadeFrames: 0,
        attackMs: 0,
        releaseMs: 0,
        tone: 0,
        eq: {low: null, mid: null, high: null},
      }));
      fixture.revision = 4;
      return {
        committedRevision: 4,
        runtimeRevision: 4,
        runtimePublished: true,
        snapshotError: null,
      };
    };
    fixture.session.deletePad = async (request) => {
      order.push(`delete:${request.slot}`);
      fixture.assigned.delete(request.slot);
      fixture.playbacks.delete(request.slot);
      fixture.revision = 4;
      return {committedRevision: 4, runtimeRevision: 4, runtimePublished: true, snapshotError: null};
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
        reverse: false,
        pitchCents: 0,
        pan: 0,
        loopMode: "forward" as const,
        loopStartFrame: null,
        loopCrossfadeFrames: 0,
        attackMs: 0,
        releaseMs: 0,
        tone: 0,
        eq: {low: null, mid: null, high: null},
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
    await act(async () => hostListener?.({state: "running", errorCode: null, errorDetails: {}}));
    await screen.findByText("Audio running");
    setRunningAudioFixture(fixture.session);
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
    fireEvent.keyDown(screen.getByRole("button", {name: "Pad A01 — assigned — Key Q"}), {
      key: "Enter",
      code: "Enter",
      repeat: false,
    });
    await waitFor(() => expect(triggerCount).toBe(1));

    if (kind === "mute") {
      selectSamplePage("Playback");
      await userEvent.click(screen.getByRole("button", {name: "Mute"}));
    } else if (kind === "reset") {
      selectSamplePage("Pad");
      await userEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
      await userEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
    } else if (kind === "delete") {
      selectSamplePage("Pad");
      await userEvent.click(screen.getByRole("button", {name: "Delete Pad A01"}));
    } else {
      selectSamplePage("Pad");
      await userEvent.click(screen.getByRole("button", {name: "Replace Sample"}));
      const input = container.querySelector<HTMLInputElement>(".sample-file-input")!;
      await userEvent.upload(input, wavFile("replace.wav"));
      await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
      await commitLongSourceSelection();
    }

    await waitFor(() => expect(order).toEqual([`stop:0`, `${kind}:0`]));
    expect(fixture.revision).toBe(4);
    if (kind === "delete") {
      await screen.findByRole("button", {name: "Pad A01 — empty — Key Q"});
      expect(screen.queryByText("33333333-3333-4333-8333-333333333333", {selector: ".sample-details dd"})).toBeNull();
      expect(screen.queryByRole("slider", {name: "Pad A01 Volume"})).toBeNull();
    }
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
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Playback");
  expect(screen.getByText("Tap a Pad to preview")).toBeTruthy();

  selectSamplePage("Playback");
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
          category: null, colour_override: null, colour: null,
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
  // D01: a card tap selects; OPEN PROJECT opens the selection.
  await userEvent.click(await screen.findByRole("button", {name: "Select Project 22222222"}));
  const openSecond = await screen.findByRole("button", {
    name: "Open Project 22222222",
  });
  fireEvent.click(openSecond);
  fireEvent.click(openSecond);

  expect(secondOpenCount).toBe(1);
  expect(screen.getByText("Project", {selector: "dt"}).nextElementSibling?.textContent)
    .toBe("11111111");
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
  await waitFor(() => expect(screen.getByTestId("creator-phase").textContent).toBe("importing"));
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
  expect(document.querySelector(".overview-bpm")?.textContent).toBe("120 BPM");
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
      // Listed but not remembered: boot stays in the library, so this test
      // observes only the retried listing, not an automatic open or create.
      return [listedSummary];
    },
  });
  render(<App runtimeFactory={() => fixture.session} />);
  expect((await screen.findByRole("alert")).textContent)
    .toContain("The local Project is busy in another tab or process.");
  await user.click(screen.getByRole("button", {name: "Retry project"}));
  await screen.findByRole("button", {name: "Open Project 11111111"});
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
  ["INVALID_PROJECT", {}, "This file is not a Project Creator can open."],
  ["DUPLICATE_ID", {},
    "The import was refused because the local copy of this Project has newer changes. Nothing was lost."],
  ["WEB_RUNTIME_RESOURCE_LIMIT", {
    resource: "ingest_decoded_frames", observed: 43200001, limit: 43200000,
  }, "This is more audio than Creator can handle at once on this device."],
  ["IO_ERROR", {storage_condition: "quota_exceeded"},
    "This device has run out of storage space for Creator."],
  ["HOST_PROTOCOL_MISMATCH", {}, "This copy of Creator is out of date."],
  ["INTERNAL_ERROR", {}, "Something went wrong in Creator."],
  ["HOST_RESTART_REQUIRED", {terminal_state: "restart-required"},
    "The audio engine stopped. Your Project is saved and not affected."],
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
  // #1680: codes and detail tokens stay out of the user-facing text.
  for (const hidden of [code, ...Object.values(details).map(String)]) {
    expect(screen.getByRole("alert").textContent).not.toContain(hidden);
  }
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

test("renders the hardware shell with a read-only overview and no fallback to a workspace", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  expect(screen.getByRole("complementary", {name: "Physical controls"})).toBeTruthy();
  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(display).queryAllByRole("link")).toHaveLength(0);
  expect(within(display).queryAllByRole("textbox")).toHaveLength(0);
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
  expect(screen.getByRole("region", {name: "Pad matrix"})).toBeTruthy();
  const touch = screen.getByRole("region", {name: "Touch workspace"});
  // The workspace shell is gone: there is no fallback control to find.
  expect(within(touch).queryByRole("button", {name: "Existing workspace"})).toBeNull();
  expect(screen.queryByRole("button", {name: "Hardware layout"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Activate audio"})).toBeNull();
  expect(within(screen.getByRole("region", {name: "Pad matrix"}))
    .getByRole("button", {name: "Pad A01 — empty — Key Q"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Project"}).getAttribute("aria-current"))
    .toBe("page");
  expect(screen.getByText("Project 11111111")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Sample"}));
  expect(screen.getByRole("heading", {name: "Sample editor"})).toBeTruthy();
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
  await user.click(screen.getByRole("button", {name: "Project"}));

  expect(screen.getByTestId("hardware-console")).toBeTruthy();
});

test("hardware Project keeps list/import/open, offers New Project in touch and omits Save As", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  const display = screen.getByRole("region", {name: "Overview display"});
  expect(within(display).queryAllByRole("button")).toHaveLength(0);
  expect(within(display).queryByRole("button", {name: "New"})).toBeNull();
  expect(within(display).getByTestId("project-overview").textContent ?? "")
    .toContain("LOCAL AUTOSAVE");

  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).getByRole("button", {name: "Open local"})).toBeTruthy();
  expect(within(touch).getByRole("button", {name: "Import .lmdj"})).toBeTruthy();
  expect(within(touch).queryByRole("button", {name: "Activate audio"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Enable MIDI"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Export report"})).toBeNull();
  // System is the brand mark on the rail, not a touch-area button, and the
  // Pad recording source is a System setting rather than a touch-area row.
  expect(within(touch).queryByRole("button", {name: "System"})).toBeNull();
  expect(within(touch).queryByRole("region", {name: "Pad recording"})).toBeNull();
  expect(within(touch).queryByRole("combobox", {name: "Pad recording source"})).toBeNull();
  await userEvent.click(within(screen.getByRole("complementary", {name: "Physical controls"}))
    .getByRole("button", {name: "System"}));
  expect(within(touch).getByRole("button", {name: "Enable MIDI"})).toBeTruthy();
  expect(within(touch).getByRole("button", {name: "Export report"})).toBeTruthy();
  await user.click(screen.getByText("Project and build details", {selector: "summary"}));
  const details = screen.getByText("Project and build details", {selector: "summary"}).parentElement!;
  expect(within(details).getByText("Rev").nextElementSibling?.textContent).toBe("4");
  expect(within(details).getByText("Project ID").nextElementSibling?.textContent)
    .toBe(ready.project.current!.projectId);
  expect(within(display).queryByText("Rev")).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Back to music"}));
  expect(within(touch).getByRole("button", {name: "New Project"})).toBeTruthy();
  expect(within(touch).queryByRole("button", {name: "Save As"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: "Export project"})).toBeNull();
  expect(within(touch).queryByRole("button", {name: /^Open$/})).toBeNull();
});

test("gates the hardware Sequence key on the same reachability as the mode rail", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  // Same state, same question, in both layouts: is Sequence reachable? The
  // workspace rail answers no and says why, because this Project has no
  // Sequence capability behind it.
  const rail = screen.getByRole("button", {name: /^Sequence/});
  expect(rail.getAttribute("aria-label"))
    .toBe("Sequence — open a playable Project first");
  expect(rail.hasAttribute("disabled")).toBe(true);

  const key = screen.getByRole("button", {name: /^Sequence/});
  expect(key.getAttribute("aria-label")).toBe(rail.getAttribute("aria-label"));
  expect(key.hasAttribute("disabled")).toBe(true);

  // The defect this gate catches: an enabled key mounted the full editor, so
  // the Tempo/Swing controls and Create Pattern looked operable while every
  // one of them hit `if (!isSequenceSession(session)) return` and reported
  // nothing at all.
  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(touch).queryByRole("region", {name: "Sequence settings"}))
    .toBeNull();
  expect(within(touch).queryByRole("slider", {name: "BPM"})).toBeNull();
});

test("keeps pad identity and mounts Project Sample Sequence in the hardware touch screen", async () => {
  const user = userEvent.setup();
  // Sequence is only reachable behind a Sequence capability, in this layout
  // exactly as in the mode rail, so this journey has to supply one to reach
  // the Sequence leg at all.
  const fixture = mutableSampleRuntimeFixture();
  const session = Object.assign(fixture.session, sequenceSessionStubs());
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));

  const padMatrix = () => screen.getByRole("region", {name: "Pad matrix"});
  const touch = () => screen.getByRole("region", {name: "Touch workspace"});
  // This fixture's snapshot assigns A1, so the identity carried across every
  // mode switch below is slot, assignment and key hint together.
  const padA1 = () => within(padMatrix()).getByRole("button", {
    name: "Pad A01 — assigned — Key Q",
  });
  expect(padA1()).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();
  expect(within(touch()).getByRole("heading", {name: "Project 11111111"})).toBeTruthy();

  await user.click(screen.getByRole("button", {name: "Sample"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("SAMPLE");
  // D03: the upper screen names the Pad and draws the whole waveform, read-only.
  const sampleOverview = screen.getByTestId("sample-overview");
  expect(document.querySelector(".overview-context")?.textContent).toBe("SAMPLE / PAD A01");
  expect(within(sampleOverview).getByRole("img", {name: /waveform/})).toBeTruthy();
  expect(within(sampleOverview).queryAllByRole("button")).toHaveLength(0);
  expect(within(screen.getByRole("region", {name: "Overview display"}))
    .queryByRole("button", {name: "Zoom In"})).toBeNull();
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getAllByRole("heading", {name: "Sample editor"})).toHaveLength(1);

  await user.click(screen.getByRole("button", {name: "Sequence"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("SEQUENCE");
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getByRole("button", {name: "Choose Pattern"}).textContent).toContain("GROOVE /");
  expect(within(touch()).getByRole("button", {name: "Choose Pattern"})).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();

  await user.click(screen.getByRole("button", {name: "Perform"}));
  expect(screen.getByTestId("overview-display").textContent ?? "").toContain("PERFORM");
  // D04's upper screen is read-only: the transport's bar and beat (from its
  // frames, as on Sequence), real Bank/Quantize facts, never the pictured
  // output meters or a control of any kind.
  expect(screen.getByTestId("perform-counter").textContent).toBe("BAR 01 / 01 · BEAT 01 / 04");
  expect(screen.getByTestId("perform-overview").textContent ?? "")
    .toMatch(/Bank.*A.*Quantize/s);
  expect(screen.getByTestId("perform-overview").textContent ?? "")
    .not.toMatch(/PEAK|NO CLIP/);
  expect(within(screen.getByRole("region", {name: "Overview display"}))
    .queryByRole("slider")).toBeNull();
  expect(within(screen.getByRole("region", {name: "Overview display"}))
    .queryByRole("button")).toBeNull();
  expect(padA1()).toBeTruthy();
  expect(within(touch()).getByRole("heading", {name: "Perform"})).toBeTruthy();
  expect(within(touch()).queryByText(/stays on the existing workspace/i)).toBeNull();
  expect(within(touch()).queryByText(/Launch and FX wait/i)).toBeTruthy();
  expect(screen.getByTestId("hardware-console")).toBeTruthy();

  await user.click(screen.getByRole("button", {name: "Project"}));
  expect(padA1()).toBeTruthy();
});

test("hardware Slice and Sound Sets stay in the touch workspace without extra physical keys", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);
  const physical = screen.getByRole("complementary", {name: "Physical controls"});
  const touch = screen.getByRole("region", {name: "Touch workspace"});
  expect(within(physical).queryByRole("button", {name: /^Slice/})).toBeNull();
  expect(within(physical).queryByRole("button", {name: /^Sound Sets/})).toBeNull();
  expect(within(touch).queryByRole("button", {name: /Slice/})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  expect(within(touch).getByRole("button", {name: /Slice/})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  expect(within(touch).getByRole("button", {name: /Sound Sets/})).toBeTruthy();
  expect(screen.getByTestId("hardware-console")).toBeTruthy();
});

const engagedTransportStatus = (
  overrides: Partial<PatternTransportStatus> = {},
): PatternTransportStatus => ({
  engaged: true,
  playing: true,
  recording: false,
  phase: "idle",
  runtimeGeneration: 1,
  transportEpoch: 1,
  originFrame: 0,
  runtimeFrame: 0,
  observedAtMilliseconds: 0,
  commandId: null,
  publicationPending: false,
  currentPatternId: null, pendingSwitch: null,
  error: null,
  ...overrides,
});

// Minimal Sequence capability stubs: only querySequenceStatus and
// listSequenceRecovery are ever awaited (by refreshSequence); the rest exist
// so isSequenceSession admits the fixture and the Sequence mode unlocks.
const sequenceSessionStubs = () => ({
  beginSequence: async () => sequenceStatusStub(),
  flushSequence: async () => sequenceStatusStub(),
  createPattern: async () => sequenceStatusStub(),
  updateSequenceSettings: async () => sequenceStatusStub(),
  editPatternEvents: async () => sequenceStatusStub(),
  disarmSequenceCapture: async () => sequenceStatusStub(),
  stopSequence: async () => sequenceStatusStub(),
  requestPatternSwitch: async () => sequenceStatusStub(),
  querySequenceStatus: async () => sequenceStatusStub(),
  listSequenceRecovery: async () => [],
  applySequenceRecovery: async () => sequenceStatusStub(),
  discardSequenceRecovery: async () => ({}),
  subscribeSequenceBarBoundary: () => () => {},
});

const sequenceStatusStub = () => ({
  state: "inactive" as const,
  sessionId: null,
  patternId: null,
  pendingPatternId: null,
  expectedRevision: 3,
  nextFlushSequence: 0,
  pendingEventCount: 0,
  effectiveRuntimeFrame: null,
});

test("a late Stop retry failure keeps the newer Record command pending", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const publishRunning = controlledSampleAudio(fixture.session);
  const retryTicket = deferred<PatternTransportTicket>();
  const retryInspection = deferred<PatternTransportStatus>();
  const recordTicket = deferred<PatternTransportTicket>();
  const requests: PatternTransportRequest[] = [];
  const wire: string[] = [];
  let runtimeTail = Promise.resolve();
  // RuntimeSession serializes request and inspect on the same action tail.
  // In particular, a poll queued during the retry submit runs before that
  // retry's trailing inspect; the new Record is queued behind that inspect.
  const serialize = <T,>(action: () => Promise<T>): Promise<T> => {
    const pending = runtimeTail.then(action);
    runtimeTail = pending.then(() => undefined, () => undefined);
    return pending;
  };
  let stopSettled = false;
  let retryInspectionStarted = false;
  let recordSettled = false;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    requestPatternTransport: (request: PatternTransportRequest) => {
      requests.push(request);
      const submission = requests.length;
      return serialize(async () => {
        wire.push(`request:${request.intent}:${submission}`);
        if (submission === 1) {
          throw Object.assign(new Error("Stop submit timed out"), {code: "HOST_TIMEOUT"});
        }
        if (submission === 2) return retryTicket.promise;
        return recordTicket.promise;
      });
    },
    inspectPatternTransport: () => serialize(async () => {
      if (requests.length < 2) return engagedTransportStatus();
      const stop = requests[1]!;
      if (!stopSettled) {
        stopSettled = true;
        wire.push("inspect:Stop settled");
        return engagedTransportStatus({
          playing: false, transportEpoch: stop.expectedEpoch, commandId: stop.commandId,
        });
      }
      if (!retryInspectionStarted) {
        retryInspectionStarted = true;
        wire.push("inspect:Stop retry tail");
        return retryInspection.promise;
      }
      const record = requests[2];
      return engagedTransportStatus({
        playing: false,
        recording: recordSettled,
        transportEpoch: recordSettled ? record!.expectedEpoch : stop.expectedEpoch,
        commandId: recordSettled ? record!.commandId : stop.commandId,
      });
    }),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await publishRunning();
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));

  vi.useFakeTimers({toFake: ["setInterval", "clearInterval"]});
  try {
    fireEvent.click(screen.getByRole("button", {name: /^Play\/Stop/}));
    await flushAsyncTurns();
    await act(async () => { await vi.advanceTimersByTimeAsync(250); });
    await flushAsyncTurns();
    expect(requests).toHaveLength(2);
    expect(requests[1]).toEqual(requests[0]);
    expect(requests[0]!.intent).toBe("play_stop");

    // Queue a second reconciliation while the identical Stop retry submit is
    // still unresolved. Its inspection will settle Stop before the older
    // reconciliation's trailing inspection can complete.
    await act(async () => { await vi.advanceTimersByTimeAsync(250); });
    await act(async () => retryTicket.resolve({
      sessionId: requests[1]!.sessionId,
      commandId: requests[1]!.commandId,
      submit: "accepted",
      status: engagedTransportStatus({
        phase: "awaiting_audio", transportEpoch: requests[1]!.expectedEpoch,
        commandId: requests[1]!.commandId,
      }),
    }));
    await flushAsyncTurns();
    expect(retryInspectionStarted).toBe(true);
    expect(transportPhase()).toBe("stopped");
    expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(false);

    fireEvent.click(screen.getByRole("button", {name: "Record"}));
    await flushAsyncTurns();
    expect(requests).toHaveLength(3);
    expect(requests[2]!.intent).toBe("record");
    expect(requests[2]!.commandId).not.toBe(requests[0]!.commandId);
    expect(requests[2]!.expectedEpoch).toBe(requests[0]!.expectedEpoch + 1);
    expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(true);
    expect(wire).toEqual([
      "request:play_stop:1", "request:play_stop:2",
      "inspect:Stop settled", "inspect:Stop retry tail",
    ]);

    await act(async () => retryInspection.reject(Object.assign(
      new Error("Old Stop inspection timed out"), {code: "HOST_TIMEOUT"},
    )));
    await flushAsyncTurns();
    expect(wire.at(-1)).toBe("request:record:3");
    // Record's own request is still unresolved. An error from the retired
    // Stop must not remove its busy state or admit another transport command.
    expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", {name: /^Play\/Stop/}).hasAttribute("disabled")).toBe(true);

    await act(async () => recordTicket.resolve({
      sessionId: requests[2]!.sessionId,
      commandId: requests[2]!.commandId,
      submit: "accepted",
      status: engagedTransportStatus({
        playing: false, phase: "awaiting_audio", transportEpoch: requests[2]!.expectedEpoch,
        commandId: requests[2]!.commandId,
      }),
    }));
    await flushAsyncTurns();
    expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(true);
    recordSettled = true;
    await act(async () => { await vi.advanceTimersByTimeAsync(250); });
    await flushAsyncTurns();
    expect(transportPhase()).toBe("recording");
    expect(screen.getByRole("button", {name: /^Record/}).hasAttribute("disabled")).toBe(false);
    fireEvent.click(screen.getByRole("button", {name: "System"}));
    fireEvent.click(screen.getByText("Developer diagnostics (1)"));
    expect(within(screen.getByRole("region", {name: "Developer diagnostics"}))
      .queryByText("Old Stop inspection timed out")).toBeNull();
  } finally {
    rendered.unmount();
    vi.useRealTimers();
  }
});

test.each(["submission", "inspection"] as const)(
  "a still-current Stop retry %s failure reports and retains that command",
  async (stage) => {
    const fixture = mutableSampleRuntimeFixture();
    const publishRunning = controlledSampleAudio(fixture.session);
    const retryTicket = deferred<PatternTransportTicket>();
    const retryInspection = deferred<PatternTransportStatus>();
    const followingRetry = deferred<PatternTransportTicket>();
    const requests: PatternTransportRequest[] = [];
    let runtimeTail = Promise.resolve();
    const serialize = <T,>(action: () => Promise<T>): Promise<T> => {
      const pending = runtimeTail.then(action);
      runtimeTail = pending.then(() => undefined, () => undefined);
      return pending;
    };
    let inspectRetry = false;
    const session = Object.assign(fixture.session, sequenceSessionStubs(), {
      requestPatternTransport: (request: PatternTransportRequest) => {
        requests.push(request);
        const submission = requests.length;
        return serialize(async () => {
          if (submission === 1) {
            throw Object.assign(new Error("Stop submit timed out"), {code: "HOST_TIMEOUT"});
          }
          return submission === 2 ? retryTicket.promise : followingRetry.promise;
        });
      },
      inspectPatternTransport: () => serialize(async () => {
        if (inspectRetry) {
          inspectRetry = false;
          return retryInspection.promise;
        }
        return engagedTransportStatus();
      }),
    });
    const rendered = render(<App initialState={ready} runtimeFactory={() => session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await publishRunning();
    await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
    await waitFor(() => expect(transportPhase()).toBe("playing"));

    vi.useFakeTimers({toFake: ["setInterval", "clearInterval"]});
    try {
      fireEvent.click(screen.getByRole("button", {name: /^Play\/Stop/}));
      await flushAsyncTurns();
      await act(async () => { await vi.advanceTimersByTimeAsync(250); });
      await flushAsyncTurns();
      expect(requests).toHaveLength(2);
      expect(requests[1]).toEqual(requests[0]);
      expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(true);

      const message = `Still-current Stop retry failed during ${stage}`;
      const error = Object.assign(new Error(message), {code: "HOST_TIMEOUT"});
      if (stage === "submission") {
        await act(async () => retryTicket.reject(error));
      } else {
        inspectRetry = true;
        await act(async () => retryTicket.resolve({
          sessionId: requests[1]!.sessionId,
          commandId: requests[1]!.commandId,
          submit: "accepted",
          status: engagedTransportStatus({
            phase: "awaiting_audio", transportEpoch: requests[1]!.expectedEpoch,
            commandId: requests[1]!.commandId,
          }),
        }));
        await flushAsyncTurns();
        await act(async () => retryInspection.reject(error));
      }
      await flushAsyncTurns();
      expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(false);
      fireEvent.click(screen.getByRole("button", {name: "System"}));
      fireEvent.click(screen.getByText("Developer diagnostics (2)"));
      const log = screen.getByRole("region", {name: "Developer diagnostics"});
      expect(within(log).getByText("Reconcile transport play_stop")).toBeTruthy();
      expect(within(log).getByText(message)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", {name: "Back to music"}));

      // The command remains the current failed identity. Inspection proving
      // its epoch still absent retries that exact identity, rather than
      // swallowing the error or inventing another toggle.
      await act(async () => { await vi.advanceTimersByTimeAsync(250); });
      await flushAsyncTurns();
      expect(requests).toHaveLength(3);
      expect(requests[2]).toEqual(requests[0]);
      expect(screen.getByRole("button", {name: "Record"}).hasAttribute("disabled")).toBe(true);
    } finally {
      rendered.unmount();
      vi.useRealTimers();
    }
  },
);

test("disengages the Pattern transport projection when the Runtime leaves ready", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => engagedTransportStatus(),
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));

  // A failed Runtime has no engagement; the projection must not keep showing
  // the retired engagement's last state.
  await act(async () => hostListener?.({
    state: "failed", errorCode: "INTERNAL_ERROR", errorDetails: {},
  }));

  await waitFor(() => expect(transportPhase()).toBe("stopped"));
});

test("re-engages the Pattern transport with a fresh identity when an open replaces the Project with the same id", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const inspectedSessionIds: string[] = [];
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async (sessionId: string) => {
      inspectedSessionIds.push(sessionId);
      return engagedTransportStatus({
        recording: inspectedSessionIds.length > 1,
        playing: inspectedSessionIds.length === 1,
      });
    },
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await waitFor(() => expect(inspectedSessionIds).toHaveLength(1));

  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  await userEvent.click(screen.getByRole("button", {name: "Open local"}));
  await userEvent.click(await screen.findByRole("button", {
    name: "Open Project 11111111",
  }));

  // The replacement retires the runtime engagement even though the Project id
  // is unchanged, so the projection re-engages under a fresh identity instead
  // of keeping the retired one's state.
  await waitFor(() => expect(inspectedSessionIds).toHaveLength(2));
  expect(inspectedSessionIds[1]).not.toBe(inspectedSessionIds[0]);
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("recording"));
});

// #1958: while the transport plays and does not record, ← → and the picker
// queue the transport's Pattern switch instead of reloading the snapshot; the
// selection follows once an inspection reports the switch applied.
const secondSwitchPattern = "66666666-6666-4666-8666-666666666666";
const secondPatternReady: CreatorState = {
  ...ready,
  project: {
    ...ready.project,
    current: {
      ...ready.project.current!,
      patterns: [
        ...ready.project.current!.patterns,
        {patternId: secondSwitchPattern, bars: 1, events: []},
      ],
    },
  },
};
// The projection refresh must keep listing the second Pattern these journeys
// step to, so inspectProject augments the fixture's single-Pattern Truth.
function withSecondPatternInspect(
  fixture: ReturnType<typeof mutableSampleRuntimeFixture>, bars = 1,
) {
  return async () => {
    const value = fixture.inspectProject();
    value.project.patterns[secondSwitchPattern] = {bars, events: []};
    return value;
  };
}
// #1958: the chained Stop case needs a third Pattern whose length differs
// from both others, so following the wrong target is distinguishable by the
// grid alone.
const thirdSwitchPattern = "77777777-7777-4777-8777-777777777777";
const chainedPatternsReady: CreatorState = {
  ...ready,
  project: {
    ...ready.project,
    current: {
      ...ready.project.current!,
      patterns: [
        ...ready.project.current!.patterns,
        {patternId: secondSwitchPattern, bars: 2, events: []},
        {patternId: thirdSwitchPattern, bars: 4, events: []},
      ],
    },
  },
};
function withChainedPatternInspect(
  fixture: ReturnType<typeof mutableSampleRuntimeFixture>,
) {
  return async () => {
    const value = fixture.inspectProject();
    value.project.patterns[secondSwitchPattern] = {bars: 2, events: []};
    value.project.patterns[thirdSwitchPattern] = {bars: 4, events: []};
    return value;
  };
}
// SETUP's Refresh playback re-inspects the transport, so a state the fake
// changed behind the app's back becomes observed without waiting on a poll
// only busy or pending states drive.
async function refreshPlaybackProjection() {
  const setup = screen.getByRole("button", {name: "SETUP"});
  if (setup.getAttribute("aria-pressed") !== "true") await userEvent.click(setup);
  const summary = screen.getByText("Playback details", {selector: "summary"});
  if (!(summary.closest("details") as HTMLDetailsElement).open) {
    await userEvent.click(summary);
  }
  await userEvent.click(screen.getByRole("button", {name: "Refresh playback"}));
}
test("a playing transport routes Pattern presses to the queued switch and follows the applied one", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const switchRequests: {patternId: string; requestId: string}[] = [];
  let playing = true;
  let queued: string | null = null;
  let currentPattern = listedSummary.patternId;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => engagedTransportStatus({
      playing,
      currentPatternId: currentPattern,
      ...(queued === null ? {} : {
        pendingSwitch: {patternId: queued, activationFrame: 96_000},
      }),
    }),
    requestTransportPatternSwitch: async (request: {patternId: string; requestId: string}) => {
      switchRequests.push({...request});
      queued = request.patternId;
      return {patternId: request.patternId, activationFrame: 96_000};
    },
  });
  render(<App initialState={secondPatternReady} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  const reloadsBefore = fixture.calls.filter((call) => call === "reloadSnapshot").length;

  await userEvent.click(forward);
  await waitFor(() => expect(switchRequests).toHaveLength(1));
  expect(switchRequests[0]!.patternId).toBe(secondSwitchPattern);
  expect(switchRequests[0]!.requestId).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
  );
  // The queued target shows in the GROOVE header while the playing Pattern
  // stays named, and nothing reloaded the snapshot.
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose Pattern"})
    .textContent).toContain("→ 02"));
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(listedSummary.patternId);
  expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
    .toBe(reloadsBefore);

  // An inspection reporting the switch applied clears the queue, and the
  // selection follows the Pattern now playing.
  await act(async () => {
    currentPattern = secondSwitchPattern;
    queued = null;
  });
  await waitFor(() => expect(screen.getByTestId("sequence-pattern")
    .getAttribute("data-pattern-id")).toBe(secondSwitchPattern));
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose Pattern"})
    .textContent).not.toContain("→"));
  expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
    .toBe(reloadsBefore);

  // Stopped again — observed through SETUP's Refresh playback, the app's own
  // reconciliation control — a picker press returns to the snapshot reload
  // path.
  await act(async () => {
    playing = false;
    queued = null;
  });
  await refreshPlaybackProjection();
  await waitFor(() => expect(transportPhase()).toBe("stopped"));
  await userEvent.click(screen.getByRole("button", {name: "Choose Pattern"}));
  await userEvent.click(within(screen.getByRole("dialog", {name: "Choose Pattern"}))
    .getByRole("button", {name: "GROOVE / 01"}));
  await waitFor(() => expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
    .toBe(reloadsBefore + 1));
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(listedSummary.patternId);
});

test("a stopped transport inspection preserves the user's selected Pattern", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const oldInspection = deferred<PatternTransportStatus>();
  let inspections = 0;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture, 2),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => {
      inspections += 1;
      if (inspections === 2) return oldInspection.promise;
      return engagedTransportStatus({
        playing: false,
        currentPatternId: listedSummary.patternId,
      });
    },
  });
  const initialState: CreatorState = {
    ...secondPatternReady,
    project: {
      ...secondPatternReady.project,
      current: {
        ...secondPatternReady.project.current!,
        patterns: secondPatternReady.project.current!.patterns.map((pattern) =>
          pattern.patternId === secondSwitchPattern ? {...pattern, bars: 2} : pattern),
      },
    },
  };
  render(<App initialState={initialState} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await waitFor(() => expect(inspections).toBeGreaterThan(0));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("stopped"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  // Start the real reconciliation path before selection, and delay only its
  // response. It observes A, then arrives after B's stopped reload succeeds.
  await refreshPlaybackProjection();
  await waitFor(() => expect(inspections).toBe(2));
  await userEvent.click(screen.getByRole("button", {name: "EDIT"}));
  await userEvent.click(forward);
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose bar"})
    .textContent).toMatch(/\/ 2$/));

  await act(async () => oldInspection.resolve(engagedTransportStatus({
    playing: false,
    currentPatternId: listedSummary.patternId,
  })));
  // The grid's length reads selection independently of the overview header.
  expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
    .toMatch(/\/ 2$/);
});

test("a switch applied before the first inspection still updates the Sequence selection", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const switchRequests: {patternId: string; requestId: string}[] = [];
  let currentPattern = listedSummary.patternId;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture, 2),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => engagedTransportStatus({
      currentPatternId: currentPattern,
      runtimeFrame: currentPattern === secondSwitchPattern ? 96_000 : 0,
    }),
    requestTransportPatternSwitch: async (request: {patternId: string; requestId: string}) => {
      switchRequests.push({...request});
      // The audio boundary lands before the request's following inspection;
      // no inspection ever observes the transient pending switch.
      currentPattern = request.patternId;
      return {patternId: request.patternId, activationFrame: 96_000};
    },
  });
  const initialState: CreatorState = {
    ...secondPatternReady,
    project: {
      ...secondPatternReady.project,
      current: {
        ...secondPatternReady.project.current!,
        patterns: secondPatternReady.project.current!.patterns.map((pattern) =>
          pattern.patternId === secondSwitchPattern ? {...pattern, bars: 2} : pattern),
      },
    },
  };
  render(<App initialState={initialState} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  const reloadsBefore = fixture.calls.filter((call) => call === "reloadSnapshot").length;

  await userEvent.click(forward);
  await waitFor(() => expect(switchRequests).toHaveLength(1));
  // The upper display already reads currentPatternId directly. The grid's
  // two-bar length independently proves the underlying selection followed.
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose bar"})
    .textContent).toMatch(/\/ 2$/));
  expect(screen.getByRole("button", {name: "Choose Pattern"}).textContent)
    .not.toContain("→");
  expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
    .toBe(reloadsBefore);
});

// #1958: a queued switch can apply with no inspection ever observing it
// playing, and the Stop's own first ticket status is then already stopped on
// the Pattern that switch applied. The selection follows that actually
// applied Pattern once — through the stopped observation, without a stopped
// snapshot reload — and later stopped telemetry cannot override it. This is a
// component-seam projection fixture, not physical audio or an executed native
// race.
test("a Stop landing after an unseen applied switch follows the applied Pattern", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const publishRunning = controlledSampleAudio(fixture.session);
  const switchRequests: {patternId: string; requestId: string}[] = [];
  const transportRequests: PatternTransportRequest[] = [];
  let playing = true;
  let queued: string | null = null;
  let currentPattern = listedSummary.patternId;
  let epoch = 1;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture, 2),
    requestPatternTransport: async (
      request: PatternTransportRequest,
    ): Promise<PatternTransportTicket> => {
      transportRequests.push(request);
      // The real Stop's ticket carries the first stopped status: the runtime
      // already settled on the applied Pattern with no pending switch left.
      playing = false;
      queued = null;
      epoch = request.expectedEpoch;
      return {
        sessionId: request.sessionId,
        commandId: request.commandId,
        submit: "accepted",
        status: engagedTransportStatus({
          playing: false,
          transportEpoch: epoch,
          commandId: request.commandId,
          currentPatternId: currentPattern,
        }),
      };
    },
    inspectPatternTransport: async () => engagedTransportStatus({
      playing,
      currentPatternId: currentPattern,
      transportEpoch: epoch,
      ...(queued === null ? {} : {
        pendingSwitch: {patternId: queued, activationFrame: 96_000},
      }),
    }),
    requestTransportPatternSwitch: async (request: {patternId: string; requestId: string}) => {
      switchRequests.push({...request});
      queued = request.patternId;
      return {patternId: request.patternId, activationFrame: 96_000};
    },
  });
  const initialState: CreatorState = {
    ...secondPatternReady,
    project: {
      ...secondPatternReady.project,
      current: {
        ...secondPatternReady.project.current!,
        patterns: secondPatternReady.project.current!.patterns.map((pattern) =>
          pattern.patternId === secondSwitchPattern ? {...pattern, bars: 2} : pattern),
      },
    },
  };
  const rendered = render(<App initialState={initialState} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await publishRunning();
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  const reloadsBefore = fixture.calls.filter((call) => call === "reloadSnapshot").length;

  // Queue B and observe the pending switch with the current Pattern still A.
  await userEvent.click(forward);
  await waitFor(() => expect(switchRequests).toHaveLength(1));
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose Pattern"})
    .textContent).toContain("→ 02"));
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(listedSummary.patternId);

  // B applies with the observation interval frozen: no inspection observes it
  // playing before Stop's ticket arrives.
  vi.useFakeTimers({toFake: ["setInterval", "clearInterval"]});
  try {
    await act(async () => {
      currentPattern = secondSwitchPattern;
      queued = null;
    });
    await flushAsyncTurns();
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 1$/);

    // The real Stop submission's ticket status is the first observation of
    // the settled transport: stopped on B, no pending switch.
    fireEvent.click(screen.getByRole("button", {name: /^Play\/Stop/}));
    await flushAsyncTurns();
    expect(transportRequests).toHaveLength(1);
    expect(transportRequests[0]!.intent).toBe("play_stop");
    expect(transportPhase()).toBe("stopped");
    // The grid's two-bar length independently proves the underlying
    // selection followed the applied Pattern; no snapshot was reloaded.
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 2$/);
    expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
      .toBe(secondSwitchPattern);
    expect(screen.getByRole("button", {name: "Choose Pattern"}).textContent)
      .not.toContain("→");
    expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
      .toBe(reloadsBefore);
    vi.useRealTimers();

    // The one stopped follow is spent: a later stopped observation reporting
    // the older Pattern cannot override the applied selection.
    await act(async () => {
      currentPattern = listedSummary.patternId;
    });
    await refreshPlaybackProjection();
    await waitFor(() => expect(transportPhase()).toBe("stopped"));
    await userEvent.click(screen.getByRole("button", {name: "EDIT"}));
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 2$/);
    expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
      .toBe(reloadsBefore);
  } finally {
    rendered.unmount();
    vi.useRealTimers();
  }
});

// #1958: chained switch requests — B applies unseen, a newer C is queued, and
// Stop cancels C while settling on B. The follow must read the transport's
// actually applied current Pattern: never the cancelled newest target C,
// never the stale pre-switch selection A.
test("a Stop cancelling a newer switch after an unseen applied one follows the applied Pattern", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const publishRunning = controlledSampleAudio(fixture.session);
  const switchRequests: {patternId: string; requestId: string}[] = [];
  const transportRequests: PatternTransportRequest[] = [];
  let playing = true;
  let queued: string | null = null;
  let currentPattern = listedSummary.patternId;
  let epoch = 1;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withChainedPatternInspect(fixture),
    requestPatternTransport: async (
      request: PatternTransportRequest,
    ): Promise<PatternTransportTicket> => {
      transportRequests.push(request);
      // Stop settles the transport on the applied B and cancels the queued C.
      playing = false;
      queued = null;
      epoch = request.expectedEpoch;
      return {
        sessionId: request.sessionId,
        commandId: request.commandId,
        submit: "accepted",
        status: engagedTransportStatus({
          playing: false,
          transportEpoch: epoch,
          commandId: request.commandId,
          currentPatternId: currentPattern,
        }),
      };
    },
    inspectPatternTransport: async () => engagedTransportStatus({
      playing,
      currentPatternId: currentPattern,
      transportEpoch: epoch,
      ...(queued === null ? {} : {
        pendingSwitch: {patternId: queued, activationFrame: 96_000},
      }),
    }),
    requestTransportPatternSwitch: async (request: {patternId: string; requestId: string}) => {
      switchRequests.push({...request});
      queued = request.patternId;
      return {patternId: request.patternId, activationFrame: 96_000};
    },
  });
  const rendered = render(<App initialState={chainedPatternsReady} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await publishRunning();
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  const reloadsBefore = fixture.calls.filter((call) => call === "reloadSnapshot").length;

  // Queue B and observe the pending switch with the current Pattern still A.
  await userEvent.click(forward);
  await waitFor(() => expect(switchRequests).toHaveLength(1));
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose Pattern"})
    .textContent).toContain("→ 02"));
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(listedSummary.patternId);

  // B applies unseen under the frozen observation loop, then C is queued from
  // the still-playing transport, and the Stop submission lands before any
  // inspection can observe B playing. The runtime stays the authority: the
  // fixture state each call reads is the state the FIFO of calls produced.
  vi.useFakeTimers({toFake: ["setInterval", "clearInterval"]});
  try {
    await act(async () => {
      currentPattern = secondSwitchPattern;
      queued = null;
    });
    await flushAsyncTurns();
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 1$/);

    fireEvent.click(forward);
    fireEvent.click(screen.getByRole("button", {name: /^Play\/Stop/}));
    await flushAsyncTurns();
    expect(switchRequests).toHaveLength(2);
    expect(switchRequests[1]!.patternId).toBe(thirdSwitchPattern);
    expect(transportRequests).toHaveLength(1);
    expect(transportRequests[0]!.intent).toBe("play_stop");
    expect(transportPhase()).toBe("stopped");
    // Two bars prove B; one would be stale A and four the cancelled C.
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 2$/);
    expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
      .toBe(secondSwitchPattern);
    expect(screen.getByRole("button", {name: "Choose Pattern"}).textContent)
      .not.toContain("→");
    expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
      .toBe(reloadsBefore);
    vi.useRealTimers();

    // The spent follow keeps the applied selection against later stopped
    // telemetry naming another Pattern.
    await act(async () => {
      currentPattern = thirdSwitchPattern;
    });
    await refreshPlaybackProjection();
    await waitFor(() => expect(transportPhase()).toBe("stopped"));
    await userEvent.click(screen.getByRole("button", {name: "EDIT"}));
    expect(screen.getByRole("button", {name: "Choose bar"}).textContent)
      .toMatch(/\/ 2$/);
    expect(fixture.calls.filter((call) => call === "reloadSnapshot").length)
      .toBe(reloadsBefore);
  } finally {
    rendered.unmount();
    vi.useRealTimers();
  }
});

// #1958: a refused switch is reported through the failure path, not thrown;
// the selection stays put.
test("a refused playing Pattern switch is reported and changes nothing", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const switchRequests: {patternId: string; requestId: string}[] = [];
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => engagedTransportStatus({
      currentPatternId: listedSummary.patternId,
    }),
    requestTransportPatternSwitch: async (request: {patternId: string; requestId: string}) => {
      switchRequests.push({...request});
      throw Object.assign(
        new Error("Pattern transport is recording"),
        {code: "HOST_STATE_INVALID", details: {reason: "pattern_transport_recording"}},
      );
    },
  });
  render(<App initialState={secondPatternReady} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  // The picker is available while playing; its press is refused by the Host.
  const picker = screen.getByRole("button", {name: "Choose Pattern"});
  await waitFor(() => expect(picker.hasAttribute("disabled")).toBe(false));
  await userEvent.click(picker);
  await userEvent.click(within(screen.getByRole("dialog", {name: "Choose Pattern"}))
    .getByRole("button", {name: "GROOVE / 02"}));
  await waitFor(() => expect(switchRequests).toHaveLength(1));
  expect(switchRequests[0]!.patternId).toBe(secondSwitchPattern);
  await waitFor(() => expect(screen.getByRole("button", {name: "Choose Pattern"})
    .textContent).not.toContain("→"));
  expect(screen.getByTestId("sequence-pattern").getAttribute("data-pattern-id"))
    .toBe(listedSummary.patternId);
  // The refusal is recorded in Developer diagnostics instead of thrown.
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  const summary = screen.getByText("Developer diagnostics (1)", {selector: "summary"});
  await userEvent.click(summary);
  const diagnostics = screen.getByRole("region", {name: "Developer diagnostics"});
  expect(within(diagnostics).getByText("Switch Pattern")).toBeTruthy();
  expect(within(diagnostics).getByText("HOST_STATE_INVALID")).toBeTruthy();
});

// #1958: playing opens the switch controls, recording keeps them closed
// (switching while recording is S3).
test("recording keeps the Pattern step and picker closed even though playing opens them", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let recording = false;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: withSecondPatternInspect(fixture),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    inspectPatternTransport: async () => engagedTransportStatus({recording}),
    requestTransportPatternSwitch: async () => {
      throw new Error("no switch is submitted while recording");
    },
  });
  render(<App initialState={secondPatternReady} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const forward = screen.getByRole("button", {name: "Pattern forward — →"});
  const picker = screen.getByRole("button", {name: "Choose Pattern"});
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(false));
  await waitFor(() => expect(picker.hasAttribute("disabled")).toBe(false));
  await act(async () => {
    recording = true;
  });
  // The recording state becomes observed through the same refresh control.
  await refreshPlaybackProjection();
  await waitFor(() => expect(forward.hasAttribute("disabled")).toBe(true));
  await waitFor(() => expect(picker.hasAttribute("disabled")).toBe(true));
});

test("a settled transport commit shows its revision even when the projection re-read never completes", async () => {
  const fixture = mutableSampleRuntimeFixture();
  // Truth is already ahead of the view (revision 5 vs 4), as a committed
  // Record-off leaves it; the first settled observation catches the view up.
  fixture.revision = 5;
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  let reReadStalled = false;
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectPatternTransport: async () => engagedTransportStatus({playing: false}),
    requestPatternTransport: async () => ({
      sessionId: "session-1",
      commandId: "command-1",
      submit: "accepted" as const,
      status: engagedTransportStatus({playing: false, transportEpoch: 2}),
    }),
    listLocalProjects: async () => reReadStalled
      ? new Promise<never>(() => {})
      : [fixture.summary()],
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await waitFor(() => expect(revisionCell()?.textContent).toBe("5"));
  await act(async () => hostListener?.({
    state: "running", errorCode: null, errorDetails: {},
  }));
  await screen.findByText("Audio running");

  // A second commit lands (revision 6), but this projection re-read can never
  // complete: the inventory read hangs. The revision display must still
  // follow the commit instead of waiting on the re-read.
  fixture.revision = 6;
  reReadStalled = true;
  await userEvent.click(screen.getByRole("button", {name: "Play/Stop"}));
  await waitFor(() => expect(revisionCell()?.textContent).toBe("6"));
});

test("a settled transport commit's completed re-read lands its events on the grid", async () => {
  const fixture = mutableSampleRuntimeFixture();
  // Boot settles on pre-commit Truth: revision 4, no event. Only after that
  // does the transport settle a Record-off commit (a new idle epoch), and
  // the commit lands as Sequence authority is re-read — so the committed
  // event can reach the grid only through the re-read that follows it.
  fixture.revision = 4;
  let transportEpoch = 1;
  let commitArmed = false;
  let committed = false;
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectPatternTransport: async () =>
      engagedTransportStatus({playing: false, transportEpoch}),
    requestPatternTransport: async () => {
      throw new Error("no transport command is submitted in this test");
    },
    querySequenceStatus: async () => {
      if (commitArmed && !committed) {
        committed = true;
        fixture.revision = 5;
      }
      return sequenceStatusStub();
    },
    inspectProject: async () => committed
      ? {
          ...fixture.inspectProject(),
          project: {
            ...fixture.inspectProject().project,
            patterns: {
              [listedSummary.patternId]: {
                bars: 1,
                events: [{
                  slot: {bank: 0, pad: 0},
                  onset_tick: 240, duration_tick: 240, velocity: 100,
                }],
              },
            },
          },
        }
      : fixture.inspectProject(),
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  const gridNote = () => document.querySelector(
    ".sequence-grid-row[data-pad='0'] [data-testid='sequence-grid-note']");
  expect(gridNote()).toBeNull();
  expect(revisionCell()?.textContent).toBe("4");

  // The revision update lands before the re-read starts, so the refresh must
  // not be rejected for naming the pre-commit revision: the refreshed
  // projection carries the committed event all the way onto the grid.
  commitArmed = true;
  transportEpoch = 2;
  await act(async () => hostListener?.({state: "running", errorCode: null, errorDetails: {}}));
  const note = await waitFor(() => {
    const found = gridNote();
    expect(found).not.toBeNull();
    return found!;
  });
  expect(note.getAttribute("data-onset-tick")).toBe("240");
  expect(revisionCell()?.textContent).toBe("5");
});


test("rail Bank changes keep the Sample slot until another Pad is chosen", async () => {
  render(<App initialState={{...ready, sample: {...ready.sample, selectedSlot: 2}}} />);
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  expect(screen.getByRole("button", {name: "Add Sample to Pad A03"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Bank B"}));
  const pads = screen.getByRole("region", {name: "Pad matrix"});
  expect(within(pads).getAllByRole("button")).toHaveLength(16);
  expect(within(pads).queryByRole("button", {name: /^Pad A/})).toBeNull();
  // A Bank key switches only the performing sixteen slots: A03 stays the one
  // current Pad, so no visible Pad is pressed and the edit object is kept
  // (#1961).
  expect(within(pads).queryByRole("button", {pressed: true})).toBeNull();
  expect(screen.getByRole("button", {name: "Add Sample to Pad A03"})).toBeTruthy();
  await userEvent.click(within(pads).getByRole("button", {name: "Pad B04 — empty — Key R"}));
  expect(screen.getByRole("button", {name: "Add Sample to Pad B04"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Bank A"}));
  expect(screen.getByRole("button", {name: "Add Sample to Pad B04"})).toBeTruthy();
});

// Synthetic pointer/input events drive the packaged controller seam; trusted
// activation and physical hearing stay with the packaged first-gesture
// journey. Keyboard, touch and MIDI strikes share the same controller
// trigger seam, whose selection dispatch is pinned in
// input_controller.test.ts.
test("a Pad strike moves the one current Pad, a Bank key does not (#1961)", async () => {
  const fixture = mutableSampleRuntimeFixture();
  fixture.assigned.set(20, "44444444-4444-4444-8444-444444444444");
  const triggers = vi.fn(async (slot: number, velocity: number, source: "pointer" | "keyboard" | "midi") =>
    ({sequence: 1, slot, velocity, source}));
  fixture.session.trigger = triggers;
  Object.assign(fixture.session, sequenceSessionStubs());
  setRunningAudioFixture(fixture.session);
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  const overview = screen.getByTestId("sequence-overview");
  const currentPad = () => within(overview).getByText("Pad").nextElementSibling?.textContent;
  expect(currentPad()).toBe("A01");
  const pointer = (type: string) => {
    const event = new MouseEvent(type, {bubbles: true, button: 0});
    Object.defineProperties(event, {
      pointerId: {value: 31}, pointerType: {value: "mouse"}, isPrimary: {value: true},
    });
    return event;
  };

  // Striking A01 establishes the one current Pad.
  const padA01 = within(screen.getByRole("region", {name: "Pad matrix"}))
    .getByRole("button", {name: "Pad A01 — assigned — Key Q"});
  fireEvent(padA01, pointer("pointerdown"));
  await waitFor(() => expect(triggers).toHaveBeenCalledExactlyOnceWith(0, 100, "pointer"));
  fireEvent(padA01, pointer("pointerup"));
  expect(currentPad()).toBe("A01");

  // A Bank key only switches the performing slots: the current Pad stays A01
  // (outside the visible Bank, so no row is highlighted) while the overview
  // window and grid jump to Bank B.
  await userEvent.click(screen.getByRole("button", {name: "Bank B"}));
  expect(currentPad()).toBe("A01");
  expect(overview.querySelector(".sequence-overview-names [data-current-pad]")).toBeNull();
  expect(document.querySelector(".sequence-grid-row[data-current-pad]")).toBeNull();
  expect(overview.querySelector(".sequence-overview-names li")?.textContent).toBe("B01 / EMPTY");

  // Striking B05 makes it the one current Pad on both surfaces.
  const pad = within(screen.getByRole("region", {name: "Pad matrix"}))
    .getByRole("button", {name: "Pad B05 — assigned — Key T"});
  fireEvent(pad, pointer("pointerdown"));
  await waitFor(() => expect(triggers).toHaveBeenLastCalledWith(20, 100, "pointer"));
  expect(triggers).toHaveBeenCalledTimes(2);
  expect(currentPad()).toBe("B05");
  expect(overview.querySelector(".sequence-overview-names [data-current-pad]")?.textContent)
    .toBe("B05 / SAMPLE");
  expect(document.querySelector(".sequence-grid-row[data-current-pad] .sequence-grid-pad")
    ?.textContent).toBe("B05");
  expect(document.querySelector('.pad[aria-current="true"] strong')?.textContent).toBe("B05");
  fireEvent(pad, pointer("pointerup"));

  // The Sample edit object is the same current Pad.
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("44444444-4444-4444-8444-444444444444");
});

test("↑/↓ steps the one current Pad into the Sample editor (#1961)", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const triggers = vi.fn(fixture.session.trigger);
  fixture.session.trigger = triggers;
  Object.assign(fixture.session, sequenceSessionStubs());
  setRunningAudioFixture(fixture.session);
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  const overview = screen.getByTestId("sequence-overview");
  const currentPad = () => within(overview).getByText("Pad").nextElementSibling?.textContent;
  expect(currentPad()).toBe("A01");
  const down = screen.getByRole("button", {name: "Next Pad — ↓"});
  await userEvent.click(down);
  await userEvent.click(down);
  expect(currentPad()).toBe("A03");
  expect(triggers).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await screen.findByRole("button", {name: "Add Sample to Pad A03"});
});

test.each(["pointerup", "pointercancel"])("Sample rail Pad %s releases a gate voice", async (releaseEvent) => {
  const triggers = vi.fn(async (slot: number, velocity: number, source: "pointer" | "keyboard" | "midi") =>
    ({sequence: 1, slot, velocity, source}));
  const releases = vi.fn(async () => true);
  const fixture = sampleRuntimeFixture({trigger: triggers, release: releases});
  setRunningAudioFixture(fixture.session);
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  const pad = within(screen.getByRole("region", {name: "Pad matrix"}))
    .getByRole("button", {name: "Pad A01 — assigned — Key Q"});
  const pointer = (type: string) => {
    const event = new MouseEvent(type, {bubbles: true, button: 0});
    Object.defineProperties(event, {
      pointerId: {value: 31}, pointerType: {value: "touch"}, isPrimary: {value: true},
    });
    return event;
  };
  fireEvent(pad, pointer("pointerdown"));
  await waitFor(() => expect(triggers).toHaveBeenCalledTimes(1));
  fireEvent(pad, pointer(releaseEvent));
  await waitFor(() => expect(releases).toHaveBeenCalledExactlyOnceWith(0, "pointer"));
  expect(pad.getAttribute("data-outcome")).toBe("idle");
});

// #1680: the reopen prompt over the existing recovery candidates.
const INTERRUPTED = Object.freeze({
  sessionId: "interrupted-session", patternId: ready.project.current!.patternId,
  bars: 1 as const, reason: "owner_lost", eventCount: 3,
});

// The Performance surface of a Runtime Session with one interrupted take.
function performanceSessionStubs(candidates: unknown[]) {
  const listed = [...candidates];
  return {
    listed,
    stubs: {
      performanceMasterCaptureStatus: () => ({state: "unconfigured", error: null}),
      subscribePerformanceMasterCaptureStatus: () => () => {},
      startPerformanceMasterCapture: vi.fn(), beginPerformanceRecording: vi.fn(),
      recordPerformanceEvent: vi.fn(), requestPerformancePatternLaunch: vi.fn(),
      flushPerformanceRecording: vi.fn(), stopPerformanceRecording: vi.fn(),
      queryPerformanceRecordingStatus: vi.fn(), assignPatternSlot: vi.fn(),
      clearPatternSlot: vi.fn(), movePatternSlot: vi.fn(),
      listPerformances: vi.fn(async () => []), inspectPerformance: vi.fn(),
      savePerformance: vi.fn(), discardPerformance: vi.fn(), renamePerformance: vi.fn(),
      deletePerformance: vi.fn(),
      listPerformanceRecovery: vi.fn(async () => [...listed]),
      applyPerformanceRecovery: vi.fn(async ({sessionId}: {sessionId: string}) => {
        listed.splice(listed.findIndex((entry) =>
          (entry as {sessionId: string}).sessionId === sessionId), 1);
        return {committedRevision: 4, replayed: false, projectRevision: 4};
      }),
      discardPerformanceRecovery: vi.fn(),
      bindPerformanceRecording: vi.fn(), beginPerformanceReplay: vi.fn(),
      stopPerformanceReplay: vi.fn(),
      queryPerformanceReplayStatus: vi.fn(() => new Promise(() => {})),
      commitPerformanceResample: vi.fn(),
    },
  };
}

function interruptedSequenceSession(
  fixture: ReturnType<typeof mutableSampleRuntimeFixture>,
  overrides: Record<string, unknown> = {},
) {
  const listed: unknown[] = [INTERRUPTED];
  const apply = vi.fn(async ({sessionId}: {sessionId: string}) => {
    listed.splice(listed.findIndex((entry) =>
      (entry as {sessionId: string}).sessionId === sessionId), 1);
    return {...sequenceStatusStub(), committedRevision: 4};
  });
  const discard = vi.fn(async (sessionId: string) => {
    listed.splice(listed.findIndex((entry) =>
      (entry as {sessionId: string}).sessionId === sessionId), 1);
    return true;
  });
  const list = vi.fn(async () => [...listed]);
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    listSequenceRecovery: list,
    applySequenceRecovery: apply,
    discardSequenceRecovery: discard,
    ...overrides,
  });
  return {session, apply, discard, list};
}

const interruptedRegion = () => screen.findByRole("region", {name: "Interrupted recording"});

test("a Project that opens with an interrupted recording asks once whether to keep it", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const {session, apply} = interruptedSequenceSession(fixture);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  expect(region.textContent).toContain("A recording stopped before it was saved (1 in Sequence)");
  expect(apply).not.toHaveBeenCalled();

  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  expect(apply).toHaveBeenCalledExactlyOnceWith({
    sessionId: "interrupted-session", destinationPatternId: null,
  });
  expect(await within(region).findByText("The interrupted recording is back in this Project."))
    .toBeTruthy();
  await userEvent.click(within(region).getByRole("button", {name: "Close"}));
  // A revision change within the same open never asks again.
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  // Manual refresh is available in SETUP > Playback details.
  await userEvent.click(screen.getByRole("button", {name: "SETUP"}));
  await userEvent.click(screen.getByText("Playback details", {selector: "summary"}));
  await userEvent.click(screen.getByRole("button", {name: "Refresh playback"}));
  await flushAsyncTurns();
  expect(screen.queryByRole("region", {name: "Interrupted recording"})).toBeNull();
});

test("a Project without interrupted recordings does not ask", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const list = vi.fn(async () => []);
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    listSequenceRecovery: list,
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(list).toHaveBeenCalled());
  await flushAsyncTurns();
  expect(screen.queryByRole("region", {name: "Interrupted recording"})).toBeNull();
});

test("Decide later leaves the recording in the Sequence recovery list", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const {session, apply, discard} = interruptedSequenceSession(fixture);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(within(region).getByRole("button", {name: "Decide later"}));
  expect(screen.queryByRole("region", {name: "Interrupted recording"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  // Manual refresh is available in SETUP > Playback details.
  await userEvent.click(screen.getByRole("button", {name: "SETUP"}));
  await userEvent.click(screen.getByText("Playback details", {selector: "summary"}));
  await userEvent.click(screen.getByRole("button", {name: "Refresh playback"}));
  expect(await screen.findByRole("button", {name: "Recover original Pattern"})).toBeTruthy();
  expect(apply).not.toHaveBeenCalled();
  expect(discard).not.toHaveBeenCalled();
  expect(screen.queryByRole("region", {name: "Interrupted recording"})).toBeNull();
});

test("a recording the Core refuses to keep stays listed and the prompt opens it", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const refusal = Object.assign(new Error("Sequence admission is unresolved"), {
    code: "INVALID_ARGUMENT",
    details: {reason: "sequence_admission_unresolved", journal_retained: true},
  });
  const {session} = interruptedSequenceSession(fixture, {
    applySequenceRecovery: vi.fn().mockRejectedValue(refusal),
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  expect(await within(region).findByText(/could not be kept here\s+\(1 in Sequence\)/)).toBeTruthy();
  await userEvent.click(within(region).getByRole("button", {name: "Open Sequence"}));
  expect(screen.getByRole("button", {name: "Sequence"}).getAttribute("aria-current")).toBe("page");
  expect(await screen.findByRole("button", {name: "Recover original Pattern"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  await userEvent.click(screen.getByText(/^Developer diagnostics/));
  expect(within(screen.getByRole("region", {name: "Developer diagnostics"}))
    .getByText("Keep interrupted Sequence recording")).toBeTruthy();
});

test("Discard removes the interrupted recording only after confirmation", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const {session, discard} = interruptedSequenceSession(fixture);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(within(region).getByRole("button", {name: "Discard…"}));
  expect(discard).not.toHaveBeenCalled();
  await userEvent.click(within(region).getByRole("button", {name: "Discard recording"}));
  expect(discard).toHaveBeenCalledExactlyOnceWith("interrupted-session");
  expect(await within(region).findByText("The interrupted recording was discarded.")).toBeTruthy();
});

test("an interrupted Performance take is kept through the Perform controller", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const take = {sessionId: "take-session", performanceId: "take", reason: "owner_lost",
    durableEventCount: 2, pendingEventCount: 0, fingerprint: "f".repeat(64)};
  const performance = performanceSessionStubs([take]);
  const session = Object.assign(fixture.session, sequenceSessionStubs(), performance.stubs);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  expect(region.textContent).toContain("(1 in Perform)");
  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  await waitFor(() => expect(performance.stubs.applyPerformanceRecovery)
    .toHaveBeenCalledWith(expect.objectContaining({sessionId: "take-session"})));
  expect(await within(region).findByText("The interrupted recording is back in this Project."))
    .toBeTruthy();
});

test("a Keep overtaken by a Runtime replacement sends none of its remaining commands", async () => {
  const first = mutableSampleRuntimeFixture();
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  first.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  const firstApply = deferred<ReturnType<typeof sequenceStatusStub> & {committedRevision: number}>();
  const listed = [
    INTERRUPTED,
    {...INTERRUPTED, sessionId: "second-interrupted-session"},
  ];
  const apply = vi.fn(() => firstApply.promise);
  const firstSession = Object.assign(first.session, sequenceSessionStubs(), {
    listSequenceRecovery: async () => [...listed],
    applySequenceRecovery: apply,
  });
  const second = mutableSampleRuntimeFixture();
  const sessions = [firstSession, interruptedSequenceSession(second).session];
  let created = 0;
  render(<App initialState={ready} runtimeFactory={() => sessions[created++]!} />);
  const region = await interruptedRegion();
  expect(region.textContent).toContain("2 recordings");
  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
  await act(async () => hostListener?.({
    state: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {},
  }));
  await waitFor(() => expect(created).toBe(2));
  await act(async () => firstApply.resolve({...sequenceStatusStub(), committedRevision: 4}));
  await flushAsyncTurns();
  expect(apply).toHaveBeenCalledTimes(1);
  // The new open asks afresh; the abandoned Keep claims no result.
  const fresh = await interruptedRegion();
  expect(within(fresh).getByRole("button", {name: "Keep recording"})).toBeTruthy();
  expect(within(fresh).queryByText(/back in this Project/)).toBeNull();
});

test("Keep reports the remainder the Sequence list was refreshed with", async () => {
  const fixture = mutableSampleRuntimeFixture();
  // The Core's list changes between reads: the first read after Keep is
  // empty, and any later read would still show the recording. The reported
  // remainder must be the read the Sequence list projected.
  let applied = false;
  let readsAfterApply = 0;
  const list = vi.fn(async () => {
    if (!applied) return [INTERRUPTED];
    readsAfterApply += 1;
    return readsAfterApply === 1 ? [] : [INTERRUPTED];
  });
  const apply = vi.fn(async () => {
    applied = true;
    return {...sequenceStatusStub(), committedRevision: 4};
  });
  const {session} = interruptedSequenceSession(fixture, {
    listSequenceRecovery: list, applySequenceRecovery: apply,
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  expect(await within(region).findByText("The interrupted recording is back in this Project."))
    .toBeTruthy();
});

test("a replacement Runtime Session asks again for the same Project", async () => {
  const first = mutableSampleRuntimeFixture();
  const second = mutableSampleRuntimeFixture();
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  first.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  const sessions = [
    interruptedSequenceSession(first).session,
    interruptedSequenceSession(second).session,
  ];
  let created = 0;
  render(<App initialState={ready} runtimeFactory={() => sessions[created++]!} />);
  const region = await interruptedRegion();
  await userEvent.click(within(region).getByRole("button", {name: "Decide later"}));
  await act(async () => hostListener?.({
    state: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {},
  }));
  await waitFor(() => expect(created).toBe(2));
  expect(await interruptedRegion()).toBeTruthy();
});

test("recovery refusal retains its full diagnostic envelope across mode navigation", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const message = "Sequence admission is unresolved; retain the recording until its input conversion is finalized, or explicitly discard it";
  const apply = vi.fn().mockRejectedValue(Object.assign(new Error(message), {
    code: "INVALID_ARGUMENT",
    details: {reason: "sequence_admission_unresolved", journal_retained: true},
  }));
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    listSequenceRecovery: async () => [{
      sessionId: "retained-session", patternId: ready.project.current!.patternId,
      bars: 1, reason: "owner_lost", eventCount: 1,
    }],
    applySequenceRecovery: apply,
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sequence"}));
  // Manual refresh is available in SETUP > Playback details.
  await userEvent.click(screen.getByRole("button", {name: "SETUP"}));
  await userEvent.click(screen.getByText("Playback details", {selector: "summary"}));
  await userEvent.click(screen.getByRole("button", {name: "Refresh playback"}));
  await userEvent.click(await screen.findByRole("button", {name: "Recover original Pattern"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent)
    .toBe("Creator could not apply that request. Try again. Details are in Developer diagnostics."));
  expect(apply).toHaveBeenCalledExactlyOnceWith({
    sessionId: "retained-session", destinationPatternId: null,
  });
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  await userEvent.click(screen.getByText("Developer diagnostics (1)"));
  const log = screen.getByRole("region", {name: "Developer diagnostics"});
  expect(within(log).getByText("Recover Sequence Pattern")).toBeTruthy();
  expect(within(log).getByText("INVALID_ARGUMENT")).toBeTruthy();
  expect(within(log).getByText(message)).toBeTruthy();
  expect(within(log).getByText(/"journal_retained": true/).textContent)
    .toContain('"reason": "sequence_admission_unresolved"');
  for (const mode of ["Sample", "Project", "Sequence"]) {
    await userEvent.click(screen.getByRole("button", {name: mode}));
    await userEvent.click(screen.getByRole("button", {name: "System"}));
    await userEvent.click(screen.getByText("Developer diagnostics (1)"));
    expect(within(screen.getByRole("region", {name: "Developer diagnostics"}))
      .getByText(message)).toBeTruthy();
  }
  expect(apply).toHaveBeenCalledTimes(1);
});


// The Pad colour tests start from the revision the mutable fixture holds, so
// the queued-commit revision and Truth agree from the first render.
const readyAtFixtureRevision: CreatorState = {
  ...ready,
  project: {...ready.project, current: {...ready.project.current!, revision: 3}},
};

test("Sample mode sets and restores the selected Pad's colour through Truth", async () => {
  const fixture = mutableSampleRuntimeFixture();
  // A01 holds a BASS asset with no override: it draws the BASS default.
  fixture.padColours.set(0, {category: "bass", colour_override: null, colour: 1});
  const requests: unknown[] = [];
  const session = Object.assign(fixture.session, {
    setPadColour: async (request: {slot: number; colour: number | null;
      expectedRevision: number}) => {
      requests.push(request);
      // The fixture stands in for Core: override first, then category.
      fixture.padColours.set(request.slot, {
        category: "bass",
        colour_override: request.colour,
        colour: request.colour ?? 1,
      });
      fixture.revision += 1;
      return {committedRevision: fixture.revision, projectRevision: fixture.revision,
        replayed: false};
    },
  });
  render(<App initialState={readyAtFixtureRevision} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  const padA01 = () => screen.getByRole("button", {name: /^Pad A01 /});
  expect(padA01().getAttribute("data-pad-colour")).toBe("1");
  selectSamplePage("Pad");
  const controls = within(screen.getByRole("region", {name: "Pad colour"}));
  expect(controls.getByTestId("pad-colour-source").textContent).toBe("BASS default");

  selectSamplePage("Pad");
  await userEvent.click(controls.getByRole("button", {name: "MELODIC colour"}));
  await waitFor(() => expect(padA01().getAttribute("data-pad-colour")).toBe("2"));
  expect(requests).toEqual([{slot: 0, colour: 2, expectedRevision: 3}]);
  expect(controls.getByTestId("pad-colour-source").textContent).toBe("Custom colour");
  // The stored override is not sent again.
  selectSamplePage("Pad");
  await userEvent.click(controls.getByRole("button", {name: "MELODIC colour"}));
  expect(requests).toHaveLength(1);

  await userEvent.click(controls.getByRole("button", {name: "Restore category default"}));
  await waitFor(() => expect(padA01().getAttribute("data-pad-colour")).toBe("1"));
  expect(requests).toEqual([
    {slot: 0, colour: 2, expectedRevision: 3},
    {slot: 0, colour: null, expectedRevision: 4},
  ]);
  expect(controls.getByTestId("pad-colour-source").textContent).toBe("BASS default");
});

test("a Pad colour queued behind another names the revision that commit left", async () => {
  const fixture = mutableSampleRuntimeFixture();
  fixture.padColours.set(0, {category: "bass", colour_override: null, colour: 1});
  const requests: Array<{slot: number; colour: number | null; expectedRevision: number}> = [];
  const session = Object.assign(fixture.session, {
    setPadColour: async (request: {slot: number; colour: number | null;
      expectedRevision: number}) => {
      requests.push(request);
      if (request.expectedRevision !== fixture.revision) {
        throw Object.assign(new Error("stale"), {code: "REVISION_CONFLICT", details: {}});
      }
      fixture.padColours.set(request.slot, {
        category: "bass",
        colour_override: request.colour,
        colour: request.colour ?? 1,
      });
      fixture.revision += 1;
      return {committedRevision: fixture.revision, projectRevision: fixture.revision,
        replayed: false};
    },
  });
  render(<App initialState={readyAtFixtureRevision} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Pad");
  const controls = within(screen.getByRole("region", {name: "Pad colour"}));
  // Two choices before either renders: the second queues behind the first.
  selectSamplePage("Pad");
  fireEvent.click(controls.getByRole("button", {name: "MELODIC colour"}));
  fireEvent.click(controls.getByRole("button", {name: "VOCAL colour"}));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests).toEqual([
    {slot: 0, colour: 2, expectedRevision: 3},
    {slot: 0, colour: 3, expectedRevision: 4},
  ]);
  // Truth accepted both: the second was not refused as a stale revision.
  await waitFor(() => expect(fixture.revision).toBe(5));
  expect(fixture.padColours.get(0)?.colour_override).toBe(3);
  await waitFor(() => expect(screen.getByRole("button", {name: /^Pad A01 /})
    .getAttribute("data-pad-colour")).toBe("3"));
  expect(controls.queryByRole("alert")).toBeNull();
});

test("a grid edit queued behind a Pad colour shows both committed changes", async () => {
  const fixture = mutableSampleRuntimeFixture();
  fixture.padColours.set(0, {category: "bass", colour_override: null, colour: 1});
  type EditRequest = Parameters<CreatorSequenceRuntimeSession["editPatternEvents"]>[0];
  let events: EditRequest["put"] = [];
  const requests: Array<{kind: string; expectedRevision: number}> = [];
  const commit = (kind: string, expectedRevision: number) => {
    requests.push({kind, expectedRevision});
    if (expectedRevision !== fixture.revision) {
      throw Object.assign(new Error("stale"), {code: "REVISION_CONFLICT", details: {}});
    }
    fixture.revision += 1;
    return {committedRevision: fixture.revision, projectRevision: fixture.revision,
      replayed: false};
  };
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectProject: async () => {
      const inspected = fixture.inspectProject();
      return {...inspected, project: {...inspected.project, patterns: {
        [listedSummary.patternId]: {bars: 1, events: events.map((event) => ({
          slot: {bank: Math.floor(event.slot / 16), pad: event.slot % 16},
          onset_tick: event.onsetTick, duration_tick: event.durationTick,
          velocity: event.velocity,
        }))},
      }}};
    },
    setPadColour: async (request: {slot: number; colour: number | null;
      expectedRevision: number}) => {
      const result = commit("colour", request.expectedRevision);
      fixture.padColours.set(request.slot, {
        category: "bass", colour_override: request.colour, colour: request.colour ?? 1,
      });
      return result;
    },
    editPatternEvents: async (request: EditRequest) => {
      const result = commit("grid", request.expectedRevision);
      events = request.put;
      return {...result, patternId: request.patternId, publication: "published" as const,
        patternPublication: {generation: 2, activationFrame: 0}, snapshotError: null};
    },
  });
  render(<App initialState={readyAtFixtureRevision} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  // Queue both before the first commit renders. Pointer events drive the
  // component's gesture mapping; this does not claim native input acceptance.
  selectSamplePage("Pad");
  fireEvent.click(screen.getByRole("button", {name: "MELODIC colour"}));
  fireEvent.click(screen.getByRole("button", {name: "Sequence"}));
  const lane = document.querySelector('.sequence-grid-row[data-pad="0"] .sequence-grid-lane')!;
  fireEvent.pointerDown(lane, {pointerId: 1, clientX: 0, clientY: 0, button: 0});
  fireEvent.pointerUp(window, {pointerId: 1});

  await waitFor(() => expect(requests).toEqual([
    {kind: "colour", expectedRevision: 3}, {kind: "grid", expectedRevision: 4},
  ]));
  expect(fixture.revision).toBe(5);
  expect(events).toEqual([{slot: 0, onsetTick: 0, durationTick: 240, velocity: 100}]);
  await waitFor(() => expect(screen.getByTestId("sequence-grid-note")
    .getAttribute("data-onset-tick")).toBe("0"));
  expect(screen.getByRole("button", {name: /^Pad A01 /})
    .getAttribute("data-pad-colour")).toBe("2");
});

test("a refused Pad colour is reported and the Pad keeps its Truth colour", async () => {
  const fixture = mutableSampleRuntimeFixture();
  fixture.padColours.set(0, {category: "bass", colour_override: null, colour: 1});
  const session = Object.assign(fixture.session, {
    setPadColour: async () => {
      throw Object.assign(new Error("refused"), {code: "HOST_STATE_INVALID", details: {}});
    },
  });
  render(<App initialState={readyAtFixtureRevision} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Pad");
  const controls = within(screen.getByRole("region", {name: "Pad colour"}));
  await userEvent.click(controls.getByRole("button", {name: "VOCAL colour"}));
  await controls.findByRole("alert");
  expect(screen.getByRole("button", {name: /^Pad A01 /}).getAttribute("data-pad-colour"))
    .toBe("1");
  expect(fixture.revision).toBe(3);
  // The refusal belongs to A01: it is not shown under another Pad's controls.
  await userEvent.click(screen.getByRole("button", {name: /^Pad A02 /}));
  selectSamplePage("Pad");
  expect(within(screen.getByRole("region", {name: "Pad colour"})).queryByRole("alert"))
    .toBeNull();
  await userEvent.click(screen.getByRole("button", {name: /^Pad A01 /}));
  selectSamplePage("Pad");
  expect(within(screen.getByRole("region", {name: "Pad colour"})).getByRole("alert"))
    .toBeTruthy();
});

test("Delete cancels a pending import and ignores its late completion", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let importSignal: AbortSignal | undefined;
  const lateImport = deferred<SampleCommit>();
  fixture.session.importAssignSample = async (_file, options) => {
    importSignal = options.signal;
    return lateImport.promise;
  };
  const requests: unknown[] = [];
  fixture.session.deletePad = async (request) => {
    requests.push(request);
    expect(importSignal?.aborted).toBe(true);
    fixture.assigned.delete(request.slot);
    fixture.playbacks.delete(request.slot);
    fixture.revision = 4;
    return {committedRevision: 4, runtimeRevision: 4, runtimePublished: true, snapshotError: null};
  };
  const {container} = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Replace Sample"}));
  await userEvent.upload(container.querySelector<HTMLInputElement>(".sample-file-input")!, wavFile("pending.wav"));
  await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
  await commitLongSourceSelection();
  await waitFor(() => expect(importSignal).toBeDefined());
  // Delete here belongs to the retained long-source dialog; the pages are inert.
  await userEvent.click(screen.getByRole("button", {name: "Delete Pad A01"}));
  await screen.findByRole("button", {name: "Pad A01 — empty — Key Q"});
  expect(requests).toEqual([{slot: 0, expectedRevision: 3}]);
  await act(async () => lateImport.resolve({committedRevision: 5,
    runtimeRevision: 5, runtimePublished: true, snapshotError: null}));
  expect(fixture.revision).toBe(4);
  expect(screen.queryByText("33333333-3333-4333-8333-333333333333", {selector: ".sample-details dd"})).toBeNull();
  selectSamplePage("Pad");
  expect(screen.getByRole("button", {name: "Delete Pad A01"}).hasAttribute("disabled")).toBe(true);
});

test("Delete failure remains visible and does not project an empty Pad", async () => {
  const fixture = mutableSampleRuntimeFixture();
  fixture.session.deletePad = async () => {
    throw Object.assign(new Error("Pad could not be saved"), {code: "IO_ERROR", details: {}});
  };
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Pad");
  await userEvent.click(screen.getByRole("button", {name: "Delete Pad A01"}));
  await screen.findByText("Creator could not save the sound on this device.", {selector: "[role=alert] p"});
  // #1680: the alert names no code; Developer diagnostics keeps it.
  expect(screen.getByText("Creator could not save the sound on this device.", {selector: "[role=alert] p"})
    .closest("[role=alert]")?.textContent).not.toContain("IO_ERROR");
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  await userEvent.click(screen.getByText(/^Developer diagnostics \(\d+\)$/));
  const deleteLog = within(screen.getByRole("region", {name: "Developer diagnostics"}));
  expect(deleteLog.getByText("Delete Pad")).toBeTruthy();
  expect(deleteLog.getByText("IO_ERROR")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Back to music"}));
  expect(screen.getByText("33333333-3333-4333-8333-333333333333", {selector: ".sample-details dd"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Pad A01 — assigned — Key Q"})).toBeTruthy();
  expect(fixture.revision).toBe(3);
});


// #1724: the Runtime refuses `sample.stop` unless audio runs, and each Host
// mutation stops the voice itself when it does. A Pad mutation must therefore
// not depend on a separate stop while audio is stopped, and must keep its
// stop-first order while audio runs.
const PRE_STOP_MUTATIONS = ["delete", "reset", "mute", "replace"] as const;
type PreStopMutation = typeof PRE_STOP_MUTATIONS[number];

function preStopFixture(order: string[]) {
  const fixture = sampleRuntimeFixture();
  let hostListener: ((state: RuntimeHostState) => void) | undefined;
  let audioRunning = false;
  fixture.session.subscribeHostState = (listener) => {
    hostListener = listener;
    return () => {};
  };
  fixture.session.stopPad = async () => {
    order.push("stop");
    if (!audioRunning) {
      throw Object.assign(new Error("runtime control is unavailable"), {
        code: "HOST_STATE_INVALID", details: {},
      });
    }
    return true;
  };
  const commit = (kind: PreStopMutation) => async () => {
    order.push(kind);
    return {committedRevision: 4, runtimeRevision: 4, runtimePublished: true, snapshotError: null};
  };
  fixture.session.deletePad = commit("delete");
  fixture.session.resetPad = commit("reset");
  fixture.session.updatePad = commit("mute");
  fixture.session.importAssignSample = commit("replace");
  const runAudio = async () => {
    audioRunning = true;
    await act(async () => hostListener?.({state: "running", errorCode: null, errorDetails: {}}));
    await screen.findByText("Audio running");
  };
  return {fixture, runAudio};
}

async function performPadMutation(kind: PreStopMutation, container: HTMLElement) {
  if (kind === "delete") {
    selectSamplePage("Pad");
    await userEvent.click(screen.getByRole("button", {name: "Delete Pad A01"}));
  } else if (kind === "reset") {
    selectSamplePage("Pad");
    await userEvent.click(screen.getByRole("button", {name: "Reset Pad to Defaults"}));
    await userEvent.click(screen.getByRole("button", {name: "Confirm reset"}));
  } else if (kind === "mute") {
    selectSamplePage("Playback");
    await userEvent.click(screen.getByRole("button", {name: "Mute"}));
  } else {
    selectSamplePage("Pad");
    await userEvent.click(screen.getByRole("button", {name: "Replace Sample"}));
    await userEvent.upload(container.querySelector<HTMLInputElement>(".sample-file-input")!, wavFile("replace.wav"));
    await userEvent.click(screen.getByRole("button", {name: "Confirm replace"}));
    await commitLongSourceSelection();
  }
}

test.each(PRE_STOP_MUTATIONS)("%s with audio stopped commits without a Runtime stop", async (kind) => {
  const order: string[] = [];
  const {fixture} = preStopFixture(order);
  const {container} = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  await performPadMutation(kind, container);
  await waitFor(() => expect(order).toEqual([kind]));
  expect(screen.queryByText("That can't be done right now.")).toBeNull();
});

test.each(PRE_STOP_MUTATIONS)("%s with audio running stops the voice before committing", async (kind) => {
  const order: string[] = [];
  const {fixture, runAudio} = preStopFixture(order);
  const {container} = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await runAudio();
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  await performPadMutation(kind, container);
  await waitFor(() => expect(order).toEqual(["stop", kind]));
});


test("Trim exposes the selected Pad inputs directly without a redundant Edit button", async () => {
  const fixture = sampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  expect(screen.queryByRole("button", {name: "Edit Pad A01"})).toBeNull();
  await userEvent.click(screen.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"}));
  expect(document.activeElement).toBe(screen.getByRole("spinbutton", {name: "Pad A01 Start time (seconds)"}));
});


test("Delete invalidates a decoding source and discards its eventual result", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const decoded = deferred<AudioBuffer>();
  const decode = vi.spyOn(OfflineAudioContext.prototype, "decodeAudioData")
    .mockImplementation(() => decoded.promise);
  fixture.session.deletePad = async (request) => {
    fixture.assigned.delete(request.slot);
    fixture.playbacks.delete(request.slot);
    fixture.revision = 4;
    return {committedRevision: 4, runtimeRevision: 4, runtimePublished: true, snapshotError: null};
  };
  try {
    const {container} = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
    await userEvent.click(screen.getByRole("button", {name: "Pad A02 — empty — Key W"}));
  await userEvent.click(await screen.findByRole("button", {name: "Add Sample to Pad A02"}));
    await userEvent.upload(container.querySelector<HTMLInputElement>(".sample-file-input")!, wavFile("decoding.wav"));
    await waitFor(() => expect(decode).toHaveBeenCalledTimes(1));
    await screen.findByText("Decoding long source…");
    selectSamplePage("Pad");
    await userEvent.click(screen.getByRole("button", {name: "Delete Pad A02"}));
    await waitFor(() => expect(fixture.revision).toBe(4));
    expect(screen.queryByText("Decoding long source…")).toBeNull();
    await act(async () => decoded.resolve({length: 8, numberOfChannels: 1,
      sampleRate: 48_000, getChannelData: () => new Float32Array(8)} as unknown as AudioBuffer));
    expect(screen.queryByRole("dialog", {name: "Pad A02 Long Source"})).toBeNull();
    expect(screen.getByRole("button", {name: "Pad A02 — empty — Key W"})).toBeTruthy();
  } finally { decode.mockRestore(); }
});


test("Delete waits for the selected Pad inspection to match the current Project revision", async () => {
  const fixture = sampleRuntimeFixture();
  const deletion = vi.spyOn(fixture.session, "deletePad");
  const state: CreatorState = {
    ...ready,
    project: {...ready.project, current: {...ready.project.current!, revision: 4}},
    sample: {...ready.sample, selectedSlot: 0, inspect: fixture.inspect, savedRevision: 3},
  };
  const props = {session: fixture.session, filePickIntent: {current: () => {}}, dispatch: vi.fn()};
  const view = render(<SampleSurface {...props} state={state} />);
  selectSamplePage("Pad");
  const remove = screen.getByRole("button", {name: "Delete Pad A01"});
  expect(remove.hasAttribute("disabled")).toBe(true);
  await userEvent.click(remove);
  expect(deletion).not.toHaveBeenCalled();
  view.rerender(<SampleSurface {...props} state={{...state,
    sample: {...state.sample, inspect: {...fixture.inspect, projectRevision: 4}},
  }} />);
  expect(remove.hasAttribute("disabled")).toBe(false);
  await userEvent.click(remove);
  await waitFor(() => expect(deletion).toHaveBeenCalledExactlyOnceWith({slot: 0, expectedRevision: 4}));
});

test("System preserves the creative page and playing transport, then restores entry focus", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const request = vi.fn(async () => {throw new Error("System must not command transport");});
  const session = Object.assign(fixture.session, sequenceSessionStubs(), {
    requestPatternTransport: request, inspectPatternTransport: async () => engagedTransportStatus(),
  });
  render(<App initialState={ready} runtimeFactory={() => session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name:"Sequence"}));
  await waitFor(() => expect(transportPhase()).toBe("playing"));
  const entry = screen.getByRole("button", {name:"System"});
  await userEvent.click(entry);
  expect(screen.queryByRole("region", {name:"Sequence editor"})).toBeNull();
  expect(screen.getByRole("button", {name:"Enable MIDI"})).toBeTruthy();
  expect(transportPhase()).toBe("playing");expect(request).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name:"Back to music"}));
  expect(screen.getByRole("region", {name:"Sequence editor"})).toBeTruthy();
  await waitFor(() => expect(document.activeElement).toBe(entry));
  expect(transportPhase()).toBe("playing");expect(request).not.toHaveBeenCalled();
});


test("returning from System preserves focus acquired by the next creative control", () => {
  const frames: FrameRequestCallback[] = [];
  const request = vi.spyOn(window, "requestAnimationFrame").mockImplementation((callback) => {
    frames.push(callback);
    return frames.length;
  });
  try {
    render(<App initialState={ready} />);
    fireEvent.click(screen.getByRole("button", {name: "System"}));
    fireEvent.click(screen.getByRole("button", {name: "Back to music"}));
    const nextControl = screen.getByRole("button", {name: "Sample"});
    act(() => {
      nextControl.focus();
      // The user can enter another control before the next browser frame.
      // Pending navigation work must not blur that new keyboard gesture.
      for (const callback of frames.splice(0)) callback(16);
    });
    expect(document.activeElement).toBe(nextControl);
  } finally {
    request.mockRestore();
  }
});

test("recovery More options leaves System and opens its Sequence destination", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const {session, apply, discard} = interruptedSequenceSession(fixture);
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  expect(screen.getByRole("button", {name: "Back to music"})).toBeTruthy();
  expect(screen.queryByRole("region", {name: "Sequence editor"})).toBeNull();
  await userEvent.click(within(region).getByRole("button", {name: "More options"}));
  expect(screen.queryByRole("button", {name: "Back to music"})).toBeNull();
  expect(screen.getByRole("region", {name: "Sequence editor"})).toBeTruthy();
  expect(screen.getByRole("button", {name: "Sequence"}).getAttribute("aria-current")).toBe("page");
  expect(apply).not.toHaveBeenCalled();
  expect(discard).not.toHaveBeenCalled();
});

test("recovery Open Sequence after a refused Keep leaves System with the take retained", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const refusal = Object.assign(new Error("Sequence admission is unresolved"), {
    code: "INVALID_ARGUMENT",
    details: {reason: "sequence_admission_unresolved", journal_retained: true},
  });
  const apply = vi.fn().mockRejectedValue(refusal);
  const {session, discard} = interruptedSequenceSession(fixture, {applySequenceRecovery: apply});
  render(<App initialState={ready} runtimeFactory={() => session} />);
  const region = await interruptedRegion();
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  await userEvent.click(within(region).getByRole("button", {name: "Keep recording"}));
  await userEvent.click(await within(region).findByRole("button", {name: "Open Sequence"}));
  expect(screen.queryByRole("button", {name: "Back to music"})).toBeNull();
  expect(screen.getByRole("region", {name: "Sequence editor"})).toBeTruthy();
  expect(await screen.findByRole("button", {name: "Recover original Pattern"})).toBeTruthy();
  expect(apply).toHaveBeenCalledExactlyOnceWith({sessionId: "interrupted-session", destinationPatternId: null});
  expect(discard).not.toHaveBeenCalled();
});


test("Sample pages keep their selection across Pad, Bank and System changes", async () => {
  const fixture = mutableSampleRuntimeFixture();
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Playback");
  expect(screen.getByRole("slider", {name: "Pad A01 Volume"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: /^Pad A02 /}));
  await screen.findByRole("button", {name: "Add Sample to Pad A02"});
  expect(screen.queryByRole("slider", {name: "Pad A01 Volume"})).toBeNull();
  expect(within(screen.getByRole("navigation", {name: "Sample pages"}))
    .getByRole("button", {name: "Playback"}).getAttribute("aria-current")).toBe("page");
  await userEvent.click(screen.getByRole("button", {name: "Bank B"}));
  // A Bank key never hijacks the Sample edit object (#1961): A02 stays
  // selected until another Pad is chosen.
  expect(screen.getByRole("button", {name: "Add Sample to Pad A02"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "System"}));
  expect(screen.queryByRole("navigation", {name: "Sample pages"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Back to music"}));
  expect(within(screen.getByRole("navigation", {name: "Sample pages"}))
    .getByRole("button", {name: "Playback"}).getAttribute("aria-current")).toBe("page");
  expect(screen.getByRole("button", {name: "Add Sample to Pad A02"})).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Project"}));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  expect(within(screen.getByRole("navigation", {name: "Sample pages"}))
    .getByRole("button", {name: "Trim"}).getAttribute("aria-current")).toBe("page");
});

test("changing Sample page cancels an unfinished pointer preview without committing it", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const runAudio = controlledSampleAudio(fixture.session);
  const preview = vi.spyOn(fixture.session, "setSamplePreview");
  const clear = vi.spyOn(fixture.session, "clearSamplePreview");
  const update = vi.spyOn(fixture.session, "updatePad");
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await expectSelectedAsset("33333333-3333-4333-8333-333333333333");
  selectSamplePage("Playback");
  const volume = screen.getByRole("slider", {name: "Pad A01 Volume"});
  runAudio();
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio running");
  fireEvent.pointerDown(volume, {pointerId: 31});
  fireEvent.change(volume, {target: {value: "-3.2"}});
  await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
  // A second input changes page before the first pointer is released.
  selectSamplePage("Tone / EQ");
  await waitFor(() => expect(clear).toHaveBeenCalledWith(0));
  expect(update).not.toHaveBeenCalled();
  expect(screen.getByRole("slider", {name: "Pad A01 Tone"})).toBeTruthy();
  fireEvent.pointerUp(window, {pointerId: 31});
  expect(update).not.toHaveBeenCalled();
  selectSamplePage("Playback");
  expect((screen.getByRole("slider", {name: "Pad A01 Volume"}) as HTMLInputElement).value).toBe("0");
});

test("trim editing before audio activation previews visually without a refused Host audition", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const preview = vi.spyOn(fixture.session, "setSamplePreview");
  const update = vi.spyOn(fixture.session, "updatePad");
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  const start = await screen.findByRole("slider", {name: /^Pad A01 Start —/});
  fireEvent.pointerDown(start, {pointerId: 55});
  fireEvent.change(start, {target: {value: "2"}});
  expect((start as HTMLInputElement).value).toBe("2");
  expect(screen.getByTestId("sample-overview-outside").getAttribute("width")).toBe("180");
  expect(preview).not.toHaveBeenCalled();
  expect(update).not.toHaveBeenCalled();
  fireEvent.keyDown(start, {key: "Escape"});
  fireEvent.pointerUp(window, {pointerId: 55});
  expect((start as HTMLInputElement).value).toBe("0");
  expect(screen.getByTestId("sample-overview-outside").getAttribute("width")).toBe("0");
  expect(update).not.toHaveBeenCalled();
  expect(fixture.revision).toBe(3);
});

test("a rejected trim preview restores both screens and cannot commit on late release", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const runAudio = controlledSampleAudio(fixture.session);
  const preview = vi.spyOn(fixture.session, "setSamplePreview")
    .mockRejectedValueOnce(new Error("preview refused"));
  const update = vi.spyOn(fixture.session, "updatePad");
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  const start = await screen.findByRole("slider", {name: /^Pad A01 Start —/});
  runAudio();
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio running");
  fireEvent.pointerDown(start, {pointerId: 52});
  fireEvent.change(start, {target: {value: "2"}});
  expect(screen.getByTestId("sample-overview-outside").getAttribute("width")).toBe("180");
  await waitFor(() => expect(preview).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByTestId("sample-overview-outside").getAttribute("width")).toBe("0"));
  expect((start as HTMLInputElement).value).toBe("0");
  fireEvent.pointerUp(window, {pointerId: 52});
  expect(update).not.toHaveBeenCalled();
  expect(fixture.revision).toBe(3);
});

async function enterEncoderSample(fixture: ReturnType<typeof mutableSampleRuntimeFixture>) {
  const runAudio = controlledSampleAudio(fixture.session);
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await userEvent.click(screen.getByRole("button", {name: "Sample"}));
  await userEvent.click(screen.getByRole("button", {name: /^Pad A01 —/}));
  await waitFor(() => expect(screen.getByRole("button", {name: "Encoder 3 — Pitch"})).toHaveProperty("disabled", false));
  runAudio();
  expect(screen.getByTestId("audio-state").textContent).toBe("Audio running");
}

test("Sample encoders preview together, fine-adjust and save one Pad change after rest", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const update = vi.fn(async (request: Parameters<CreatorSampleRuntimeSession["updatePad"]>[0]) => {
    fixture.playbacks.set(request.slot, {...request.playback});
    fixture.revision += 1;
    return {committedRevision: fixture.revision, runtimeRevision: fixture.revision,
      runtimePublished: true, snapshotError: null};
  });
  fixture.session.updatePad = update;
  await enterEncoderSample(fixture);
  vi.useFakeTimers();
  try {
    fireEvent.keyDown(screen.getByRole("button", {name: "Encoder 3 — Pitch"}), {key: "ArrowUp", shiftKey: true});
    await act(async () => {await Promise.resolve();});
    expect(document.querySelector('.encoder-readbacks [data-encoder="3"]')?.textContent).toContain("0.1 st");
    fireEvent.click(screen.getByRole("button", {name: "Pad Sound"}));
    fireEvent.keyDown(screen.getByRole("button", {name: "Encoder 1 — Pad Volume"}), {key: "ArrowDown"});
    await act(async () => {vi.advanceTimersByTime(399);});
    expect(update).not.toHaveBeenCalled();
    await act(async () => {vi.advanceTimersByTime(1); for (let i = 0; i < 40; i++) await Promise.resolve();});
    expect(update).toHaveBeenCalledTimes(1);
    expect(update.mock.calls[0]![0].playback).toMatchObject({pitchCents: 10, gainMillidb: -1000});
    expect(fixture.playbacks.get(0)).toMatchObject({pitchCents: 10, gainMillidb: -1000});
  } finally {vi.useRealTimers();}
});

test.each(["page", "Sample subpage", "Pad", "System", "Esc", "blur"])("%s navigation cancels unsubmitted Sample encoder edits", async (boundary) => {
  const fixture = mutableSampleRuntimeFixture();
  const update = vi.fn(fixture.session.updatePad);
  fixture.session.updatePad = update;
  const clear = vi.fn(fixture.session.clearSamplePreview);
  fixture.session.clearSamplePreview = clear;
  const preview = vi.spyOn(fixture.session, "setSamplePreview");
  await enterEncoderSample(fixture);
  vi.useFakeTimers();
  try {
    fireEvent.keyDown(screen.getByRole("button", {name: "Encoder 3 — Pitch"}), {key: "ArrowUp"});
    await act(async () => {await Promise.resolve();});
    expect(preview).toHaveBeenCalledTimes(1);
    if (boundary === "page") fireEvent.click(screen.getByRole("button", {name: "Project"}));
    else if (boundary === "Sample subpage") selectSamplePage("Tone / EQ");
    else if (boundary === "Pad") fireEvent.click(screen.getByRole("button", {name: /^Pad A02 —/}));
    else if (boundary === "System") fireEvent.click(screen.getByRole("button", {name: "System"}));
    else if (boundary === "Esc") fireEvent.keyDown(window, {key: "Escape"});
    else fireEvent.blur(window);
    await act(async () => {vi.advanceTimersByTime(400); for (let i = 0; i < 40; i++) await Promise.resolve();});
    expect(update).not.toHaveBeenCalled();
    expect(clear).toHaveBeenCalledWith(0);
    expect(fixture.playbacks.get(0)!.pitchCents).toBe(0);
  } finally {vi.useRealTimers();}
});

// Real IndexedDB requests read the stored value; only their success delivery
// to the consumer is deferred. Other Host settings keep their normal reads.
function deferMonitorPreferenceReads() {
  const pending: (() => void)[] = [];
  const get = IDBObjectStore.prototype.get;
  const spy = vi.spyOn(IDBObjectStore.prototype, "get").mockImplementation(function (this: IDBObjectStore, key) {
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
  return {pending, restore: () => spy.mockRestore()};
}

test("output-volume restore visibly gates musical input until the same session restores zero", async () => {
  const factory = new IDBFactory();
  await writeMonitorVolumePreference(0, factory);
  const reads = deferMonitorPreferenceReads();
  vi.stubGlobal("indexedDB", factory);
  const fixture = mutableSampleRuntimeFixture();
  const publishRunning = controlledSampleAudio(fixture.session);
  const activate = vi.spyOn(fixture.session, "activateAudio");
  const trigger = vi.spyOn(fixture.session, "trigger").mockImplementation(async (slot, velocity, source) =>
    ({sequence: 1, slot, velocity, source}));
  const setMonitorVolume = vi.fn();
  const requestTransport = vi.fn();
  Object.assign(fixture.session, sequenceSessionStubs(), {
    monitorVolume: () => 100, monitorDestination: () => null, setMonitorVolume,
    requestPatternTransport: requestTransport,
    inspectPatternTransport: async () => engagedTransportStatus({playing: false}),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  try {
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await waitFor(() => expect(reads.pending).toHaveLength(1));
    const pad = screen.getByRole("button", {name: /^Pad A01 —/});
    // This fails on the previous consumer: the musical Pad looks available
    // even though activateAudio will silently refuse its first gesture.
    expect(pad).toHaveProperty("disabled", true);
    expect(screen.getByRole("status", {name: "Output volume restore status"}).textContent)
      .toBe("Restoring output volume…");
    expect(screen.getByTestId("creator-phase").textContent).toBe("ready");
    expect(screen.getByRole("button", {name: /^Play\/Stop/})).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", {name: "Record"})).toHaveProperty("disabled", true);
    fireEvent.keyDown(window, {key: "q", code: "KeyQ"});
    fireEvent.keyUp(window, {key: "q", code: "KeyQ"});
    expect(activate).not.toHaveBeenCalled();
    expect(trigger).not.toHaveBeenCalled();
    expect(requestTransport).not.toHaveBeenCalled();
    expect(setMonitorVolume).not.toHaveBeenCalled();

    await act(async () => {reads.pending.shift()!();});
    await waitFor(() => expect(setMonitorVolume).toHaveBeenCalledExactlyOnceWith(0));
    expect(screen.queryByRole("status", {name: "Output volume restore status"})).toBeNull();
    expect(pad).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", {name: /^Play\/Stop/})).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", {name: "Record"})).toHaveProperty("disabled", false);
    expect(screen.getByRole("button", {name: "Encoder 4 — Output Volume"})).toHaveProperty("disabled", false);

    // jsdom cannot provide browser-trusted activation. Use the established
    // running-audio seam for the far-side musical admission after restore.
    publishRunning();
    fireEvent.keyDown(window, {key: "q", code: "KeyQ"});
    await waitFor(() => expect(trigger).toHaveBeenCalledTimes(1));
    expect(trigger.mock.calls[0]![0]).toBe(0);
    expect(trigger.mock.calls[0]![2]).toBe("keyboard");
    expect(pad.getAttribute("data-outcome")).toBe("admitted");
    fireEvent.keyUp(window, {key: "q", code: "KeyQ"});
    expect(fixture.revision).toBe(3);
  } finally {
    rendered.unmount();
    await act(async () => {for (const notify of reads.pending.splice(0)) notify();});
    reads.restore();
    vi.unstubAllGlobals();
  }
});

test("output-volume restore from a retired session cannot unlock its replacement", async () => {
  const factory = new IDBFactory();
  await writeMonitorVolumePreference(30, factory);
  const reads = deferMonitorPreferenceReads();
  vi.stubGlobal("indexedDB", factory);
  const first = mutableSampleRuntimeFixture();
  const second = mutableSampleRuntimeFixture();
  const firstVolume = vi.fn();
  const secondVolume = vi.fn();
  Object.assign(first.session, {monitorVolume: () => 100, monitorDestination: () => null, setMonitorVolume: firstVolume});
  Object.assign(second.session, {monitorVolume: () => 100, monitorDestination: () => null, setMonitorVolume: secondVolume});
  let restart!: (state: RuntimeHostState) => void;
  first.session.subscribeHostState = (listener) => {restart = listener; return () => {};};
  const sessions = [first.session, second.session];
  let created = 0;
  const rendered = render(<App initialState={ready} runtimeFactory={() => sessions[created++]!} />);
  try {
    await waitFor(() => expect(first.calls).toContain("reloadSnapshot"));
    await waitFor(() => expect(reads.pending).toHaveLength(1));
    await writeMonitorVolumePreference(0, factory);
    await act(async () => restart({state: "restart-required", errorCode: "HOST_RESTART_REQUIRED", errorDetails: {}}));
    await waitFor(() => expect(created).toBe(2));
    await waitFor(() => expect(second.calls).toContain("reloadSnapshot"));
    await waitFor(() => expect(reads.pending).toHaveLength(2));
    await act(async () => {reads.pending.shift()!();});
    expect(firstVolume).not.toHaveBeenCalled();
    expect(secondVolume).not.toHaveBeenCalled();
    expect(screen.getByRole("status", {name: "Output volume restore status"}).textContent)
      .toBe("Restoring output volume…");
    expect(screen.getByRole("button", {name: /^Pad A01 —/})).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", {name: "Encoder 4 — Output Volume"})).toHaveProperty("disabled", true);
    await act(async () => {reads.pending.shift()!();});
    await waitFor(() => expect(secondVolume).toHaveBeenCalledExactlyOnceWith(0));
    expect(firstVolume).not.toHaveBeenCalled();
    expect(screen.queryByRole("status", {name: "Output volume restore status"})).toBeNull();
    expect(screen.getByRole("button", {name: /^Pad A01 —/})).toHaveProperty("disabled", false);
  } finally {
    rendered.unmount();
    await act(async () => {for (const notify of reads.pending.splice(0)) notify();});
    reads.restore();
    vi.unstubAllGlobals();
  }
});

test("ENC4 restores device volume, remains available in System and changes no Project Truth", async () => {
  const factory = new IDBFactory();
  vi.stubGlobal("indexedDB", factory);
  try {
    await writeMonitorVolumePreference(24, factory);
    const fixture = mutableSampleRuntimeFixture();
    const setMonitorVolume = vi.fn();
    Object.assign(fixture.session, {monitorVolume: () => 24, monitorDestination: () => null, setMonitorVolume});
    render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
    await waitFor(() => expect(setMonitorVolume).toHaveBeenCalledWith(24));
    const output = screen.getByRole("button", {name: "Encoder 4 — Output Volume"});
    await waitFor(() => expect(output).toHaveProperty("disabled", false));
    fireEvent.keyDown(output, {key: "ArrowDown", shiftKey: true});
    expect(setMonitorVolume).toHaveBeenLastCalledWith(23);
    await userEvent.click(screen.getByRole("button", {name: "System"}));
    expect(screen.getByRole("button", {name: /^Encoder 1 — unassigned/})).toHaveProperty("disabled", true);
    fireEvent.keyDown(output, {key: "ArrowDown"});
    expect(setMonitorVolume).toHaveBeenLastCalledWith(22);
    expect(await readMonitorVolumePreference(factory)).toBe(22);
    expect(fixture.revision).toBe(3);
    expect(fixture.playbacks.get(0)!.gainMillidb).toBe(0);
  } finally {vi.unstubAllGlobals();}
});


test("Undo cancels the Sample turn before restoring history instead of saving the preview", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const order: string[] = [];
  const update = vi.fn(fixture.session.updatePad);
  fixture.session.updatePad = update;
  fixture.session.clearSamplePreview = async () => {order.push("cancel"); return true;};
  const undo = vi.fn(async () => {
    order.push("undo"); fixture.revision += 1;
    return {committedRevision: fixture.revision, runtimeRevision: fixture.revision,
      runtimePublished: true, snapshotError: null};
  });
  Object.assign(fixture.session, {inspectAuthoringHistory: async () => ({sessionId: "history", projectRevision: fixture.revision,
    canUndo: true, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "", disabledReason: ""}), undoAuthoring: undo, redoAuthoring: vi.fn()});
  await enterEncoderSample(fixture);
  await waitFor(() => expect(screen.getByRole("button", {name: "Undo — SHIFT + ←"}).classList.contains("is-lit")).toBe(true));
  vi.useFakeTimers();
  try {
    fireEvent.keyDown(screen.getByRole("button", {name: "Encoder 3 — Pitch"}), {key: "ArrowUp"});
    await act(async () => {for (let i = 0; i < 10; i++) await Promise.resolve();});
    fireEvent.keyDown(window, {code: "KeyZ", ctrlKey: true});
    await act(async () => {for (let i = 0; i < 40; i++) await Promise.resolve(); vi.advanceTimersByTime(400);});
    expect(undo).toHaveBeenCalledTimes(1);
    expect(order.indexOf("cancel")).toBeLessThan(order.indexOf("undo"));
    expect(update).not.toHaveBeenCalled();
    expect(fixture.revision).toBe(4);
  } finally {vi.useRealTimers();}
});

test("pure page navigation preserves ready Undo without another authority read", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const historyStatus = {sessionId: "history", projectRevision: fixture.revision,
    canUndo: true, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "", disabledReason: ""};
  const inspect = vi.fn(async () => historyStatus);
  const held = deferred<typeof historyStatus>();
  Object.assign(fixture.session, sequenceSessionStubs(), {
    inspectAuthoringHistory: inspect, undoAuthoring: vi.fn(), redoAuthoring: vi.fn(),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    await flushAsyncTurns();
    const reads = inspect.mock.calls.length;
    inspect.mockImplementation(() => held.promise);
    for (const name of ["Sample", "Sequence", "Perform", "Project"]) {
      await act(async () => {fireEvent.click(screen.getByRole("button", {name}));});
      await flushAsyncTurns();
      expect(screen.getByRole("button", {name}).getAttribute("aria-current")).toBe("page");
      fireEvent.click(screen.getByRole("button", {name: "SHIFT — engage the Undo/Redo layer"}));
      expect(undo().classList.contains("is-lit"), `${name} keeps ready global Undo`).toBe(true);
      expect(undo()).toHaveProperty("disabled", false);
      expect(inspect, `${name} does not invalidate unchanged history`).toHaveBeenCalledTimes(reads);
    }
    expect(fixture.revision).toBe(3);
  } finally {
    rendered.unmount();
    await act(async () => {held.resolve(historyStatus);});
  }
});

test("discarding the last Performance recovery refreshes Undo without a revision or page change", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const take = {sessionId: "take-session", performanceId: "take", reason: "owner_lost",
    durableEventCount: 2, pendingEventCount: 0, fingerprint: "f".repeat(64)};
  const performance = performanceSessionStubs([take]);
  const discard = vi.fn(async () => {performance.listed.splice(0); return true;});
  const inspect = vi.fn(async () => ({sessionId: "history", projectRevision: fixture.revision,
    canUndo: performance.listed.length === 0, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "",
    disabledReason: performance.listed.length > 0 ? "performance_recovery_pending" : ""}));
  Object.assign(fixture.session, sequenceSessionStubs(), performance.stubs, {
    discardPerformanceRecovery: discard, inspectAuthoringHistory: inspect,
    undoAuthoring: vi.fn(), redoAuthoring: vi.fn(),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    const region = await interruptedRegion();
    await screen.findByText("Resolve the pending recording recovery first.");
    expect(undo().classList.contains("is-lit")).toBe(false);
    const reads = inspect.mock.calls.length;
    await userEvent.click(within(region).getByRole("button", {name: "Discard…"}));
    await userEvent.click(within(region).getByRole("button", {name: "Discard recording"}));
    await within(region).findByText("The interrupted recording was discarded.");
    expect(discard).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    expect(inspect.mock.calls.length).toBeGreaterThan(reads);
    expect(fixture.revision).toBe(3);
    expect(screen.getByRole("button", {name: "Project"}).getAttribute("aria-current")).toBe("page");
  } finally {rendered.unmount();}
});

test("transport publication settlement refreshes Undo without a phase, revision or page change", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let publicationPending = true;
  const inspect = vi.fn(async () => ({sessionId: "history", projectRevision: fixture.revision,
    canUndo: !publicationPending, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "",
    disabledReason: publicationPending ? "pattern_transport_busy" : ""}));
  const transportInspect = vi.fn(async () => engagedTransportStatus({playing: false, publicationPending}));
  Object.assign(fixture.session, sequenceSessionStubs(), {
    requestPatternTransport: async () => {throw new Error("No transport command belongs to this test");},
    inspectPatternTransport: transportInspect, inspectAuthoringHistory: inspect,
    undoAuthoring: vi.fn(), redoAuthoring: vi.fn(),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    await waitFor(() => expect(transportInspect).toHaveBeenCalled());
    await screen.findByText("Stop Pattern playback to undo or redo.");
    await flushAsyncTurns();
    const reads = inspect.mock.calls.length;
    publicationPending = false;
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    expect(inspect.mock.calls.length).toBeGreaterThan(reads);
    expect(fixture.revision).toBe(3);
    expect(screen.getByRole("button", {name: "Project"}).getAttribute("aria-current")).toBe("page");
  } finally {rendered.unmount();}
});

test("page navigation retries blocked history while focus still refreshes ready history", async () => {
  const fixture = mutableSampleRuntimeFixture();
  let blocked = true;
  const inspect = vi.fn(async () => ({sessionId: "history", projectRevision: fixture.revision,
    canUndo: !blocked, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "",
    disabledReason: blocked ? "sample_import_pending" : ""}));
  Object.assign(fixture.session, {
    inspectAuthoringHistory: inspect, undoAuthoring: vi.fn(), redoAuthoring: vi.fn(),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await screen.findByText("Wait for the sound import to finish.");
    await flushAsyncTurns();
    const blockedReads = inspect.mock.calls.length;
    blocked = false;
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    expect(inspect.mock.calls.length).toBeGreaterThan(blockedReads);
    const readyReads = inspect.mock.calls.length;
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    await flushAsyncTurns();
    expect(inspect).toHaveBeenCalledTimes(readyReads);
    fireEvent.focus(window);
    await waitFor(() => expect(inspect).toHaveBeenCalledTimes(readyReads + 1));
    expect(undo().classList.contains("is-lit")).toBe(true);
  } finally {rendered.unmount();}
});

test("page navigation rechecks ready history after a reported authoring failure", async () => {
  const fixture = mutableSampleRuntimeFixture();
  const historyStatus = {sessionId: "history", projectRevision: fixture.revision,
    canUndo: true, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "", disabledReason: ""};
  const inspect = vi.fn(async () => historyStatus);
  const held = deferred<typeof historyStatus>();
  fixture.session.updatePad = async () => {
    throw Object.assign(new Error("Authoring acknowledgement lost"), {code: "IO_ERROR"});
  };
  Object.assign(fixture.session, {
    inspectAuthoringHistory: inspect, undoAuthoring: vi.fn(), redoAuthoring: vi.fn(),
  });
  const rendered = render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    selectSamplePage("Playback");
    await userEvent.click(await screen.findByRole("button", {name: "Reverse"}));
    await screen.findByRole("alert");
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    await flushAsyncTurns();
    const reads = inspect.mock.calls.length;
    inspect.mockImplementation(() => held.promise);
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    expect(inspect).toHaveBeenCalledTimes(reads + 1);
    expect(undo().classList.contains("is-lit")).toBe(false);
    await act(async () => {held.resolve(historyStatus);});
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    expect(fixture.revision).toBe(3);
  } finally {
    rendered.unmount();
    await act(async () => {held.resolve(historyStatus);});
  }
});

test("navigation retains history inspection after a Slice adoption fails after unmount", async () => {
  let resultUnknown = false;
  const historyStatus = () => ({sessionId: "history", projectRevision: 3,
    canUndo: !resultUnknown, canRedo: false, undoCount: 1, redoCount: 0,
    undoLabel: "Import sample", redoLabel: "",
    disabledReason: resultUnknown ? "authoring_history_result_unknown" : ""});
  const inspect = vi.fn(async () => historyStatus());
  const fixture = await candidatePlaybackFixture(false, current => {
    Object.assign(current.session, {inspectAuthoringHistory: inspect,
      undoAuthoring: vi.fn(), redoAuthoring: vi.fn()});
  });
  const pending = deferred<Awaited<ReturnType<typeof fixture.adopt>>>();
  fixture.adopt.mockImplementationOnce(() => pending.promise);
  const undo = () => screen.getByRole("button", {name: "Undo — SHIFT + ←"});
  try {
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
    await waitFor(() => expect(fixture.adopt).toHaveBeenCalledTimes(1));
    await userEvent.click(screen.getByRole("button", {name: "Project"}));
    await flushAsyncTurns();
    await waitFor(() => expect(undo().classList.contains("is-lit")).toBe(true));
    const reads = inspect.mock.calls.length;
    // The request was issued by the retired Slice component. Its local catch
    // does not report diagnostics, and no authoring revision reaches App.
    resultUnknown = true;
    await act(async () => {pending.reject(Object.assign(
      new Error("Adoption acknowledgement lost"), {code: "IO_ERROR"}));});
    await flushAsyncTurns();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(inspect).toHaveBeenCalledTimes(reads);
    await userEvent.click(screen.getByRole("button", {name: "Sample"}));
    expect(inspect).toHaveBeenCalledTimes(reads + 1);
    await screen.findByText("Checking whether the last change was saved…");
    expect(undo().classList.contains("is-lit")).toBe(false);
    expect(fixture.revision).toBe(3);
  } finally {
    pending.reject(new Error("test ended"));
  }
});

test("Project encoder selection does not open a Project until explicit OPEN", async () => {
  const summaries = [listedSummary, {...listedSummary, projectId: "44444444-4444-4444-8444-444444444444"},
    {...listedSummary, projectId: "55555555-5555-4555-8555-555555555555"}];
  const open = vi.fn(async () => ({}));
  const fixture = runtimeFixture({listLocalProjects: async () => summaries, openProject: open});
  render(<App initialState={ready} runtimeFactory={() => fixture.session} />);
  await waitFor(() => expect(fixture.calls).toContain("reloadSnapshot"));
  await waitFor(() => expect(screen.getByRole("button", {name: "Open Project 11111111"})).toHaveProperty("disabled", false));
  const before = open.mock.calls.length;
  const select = screen.getByRole("button", {name: "Encoder 1 — Select Project"});
  await waitFor(() => expect(select).toHaveProperty("disabled", false));
  await act(async () => {
    fireEvent.keyDown(select, {key: "ArrowUp"});
    fireEvent.keyDown(select, {key: "ArrowUp"});
  });
  expect(Array.from(document.querySelectorAll(".project-card"), (card) => [card.getAttribute("aria-label"), card.getAttribute("aria-pressed")])).toEqual([["Select Project 11111111", "false"], ["Select Project 44444444", "false"], ["Select Project 55555555", "true"]]);
  expect(open).toHaveBeenCalledTimes(before);
  await userEvent.click(screen.getByRole("button", {name: "Open Project 55555555"}));
  await waitFor(() => expect(open).toHaveBeenCalledTimes(before + 1));
});
