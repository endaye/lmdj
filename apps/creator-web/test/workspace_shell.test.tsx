import {readFileSync} from "node:fs";

import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterAll, beforeAll, expect, test} from "vitest";

import {App} from "../src/app";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import type {
  CreatorRuntimeSession,
  CreatorSampleRuntimeSession,
  LocalProjectSummary,
  RuntimeHostState,
  WaveformEnvelope,
  WaveformQuery,
} from "../src/runtime/runtime_types";

const creatorStyles = readFileSync("src/styles.css", "utf8");
let styleElement: HTMLStyleElement;
beforeAll(() => {
  styleElement = document.createElement("style");
  styleElement.textContent = creatorStyles;
  document.head.append(styleElement);
});
afterAll(() => styleElement.remove());

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
    },
  },
  runtime: {phase: "ready", errorCode: null},
};

test("enables keyboard-reachable Sample while preserving the other mode states", async () => {
  const user = userEvent.setup();
  render(<App initialState={ready} />);

  const projectMode = screen.getByRole("button", {name: "Project"});
  expect(projectMode.hasAttribute("disabled")).toBe(false);
  const sampleMode = screen.getByRole("button", {name: "Sample"});
  expect(sampleMode.hasAttribute("disabled")).toBe(false);
  expect(sampleMode.tabIndex).toBe(0);
  for (const [mode, stage] of [
    ["Sequence", 9],
    ["Perform", 10],
  ] as const) {
    const button = screen.getByRole("button", {
      name: `${mode} — available in Stage ${stage}`,
    });
    expect(button.hasAttribute("disabled")).toBe(true);
    expect(button.tabIndex).toBe(-1);
  }

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

  await user.tab();
  expect(document.activeElement).toBe(
    screen.getByRole("button", {name: "Activate audio"}),
  );
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

test("contains Replace focus, cancels with Escape, and restores the target Pad", async () => {
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
  fireEvent.drop(pad, {
    dataTransfer: {files: [new File(["wav"], "replace.wav", {type: "audio/wav"})]},
  });

  const dialog = screen.getByRole("dialog", {name: "Replace Pad A1?"});
  const cancel = screen.getByRole("button", {name: "Cancel replace"});
  const confirm = screen.getByRole("button", {name: "Confirm replace"});
  expect(dialog.getAttribute("aria-modal")).toBe("true");
  expect(document.activeElement).toBe(cancel);
  expect(sampleMode.closest("[inert]")).not.toBeNull();

  confirm.focus();
  fireEvent.keyDown(dialog, {key: "Tab"});
  expect(document.activeElement).toBe(cancel);
  fireEvent.keyDown(dialog, {key: "Escape"});
  expect(screen.queryByRole("dialog", {name: "Replace Pad A1?"})).toBeNull();
  expect(document.activeElement).toBe(pad);
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
          contract: "lmdj.project.v1",
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
          patterns: {},
          takes: {},
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
      product_build: "1.0.20.0",
      host_id: "creator-web",
      host_version: "1.1.2",
      platform_version: "0.2.1",
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
          contract: "lmdj.project.v1",
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
          patterns: {},
          takes: {},
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
    new File(["wav"], "import.wav", {type: "audio/wav"}),
  );
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
      contract: "lmdj.project.v1",
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
      patterns: {},
      takes: {},
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
  ["DUPLICATE_ID", {}, "The Project conflicts with existing local data."],
  ["WEB_RUNTIME_RESOURCE_LIMIT", {
    resource: "decoded_frames_per_pad", observed: 240001, limit: 240000,
  }, "decoded_frames_per_pad: observed 240001, limit 240000."],
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
