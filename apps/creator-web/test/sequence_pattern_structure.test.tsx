import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {App} from "../src/app";
import type {CreatorRuntimeSession} from "../src/runtime/runtime_types";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// A fake Host whose Project Truth is a set of Patterns: SETUP's resize and
// copy (#1823) change that Truth, and every read (inspect, listing revision)
// derives from it. The transport is engaged and stopped.
function structureFixture() {
  const truth = {
    revision: 0,
    patterns: {[PATTERN_ID]: {bars: 1 as 1 | 2 | 4 | 8, events: [] as unknown[]}} as
      Record<string, {bars: 1 | 2 | 4 | 8; events: unknown[]}>,
  };
  const resizePattern = vi.fn(async (request: {
    patternId: string; bars: 1 | 2 | 4 | 8; expectedRevision: number;
  }) => {
    truth.patterns[request.patternId]!.bars = request.bars;
    truth.revision += 1;
    return {
      committedRevision: truth.revision, projectRevision: truth.revision,
      patternId: request.patternId, bars: request.bars, replayed: false,
      publication: "published" as const,
      patternPublication: {generation: 2, activationFrame: 0}, snapshotError: null,
    };
  });
  const copyPattern = vi.fn(async (request: {
    sourcePatternId: string; patternId: string; expectedRevision: number;
  }) => {
    const source = truth.patterns[request.sourcePatternId]!;
    truth.patterns[request.patternId] = {bars: source.bars, events: [...source.events]};
    truth.revision += 1;
    return {
      committedRevision: truth.revision, projectRevision: truth.revision,
      sourcePatternId: request.sourcePatternId, patternId: request.patternId,
      patternSlot: null, replayed: false,
    };
  });
  const sequenceStatus = async () => ({
    state: "inactive" as const, sessionId: null, patternId: null, pendingPatternId: null,
    expectedRevision: truth.revision, nextFlushSequence: 1, pendingEventCount: 0,
    effectiveRuntimeFrame: null,
  });
  const unexpected = (name: string) => async () => { throw new Error(`${name} is not expected`); };
  const session = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => [{
      projectId: PROJECT_ID, patternId: PATTERN_ID, revision: truth.revision, bpm: 120,
      assetCount: 0, assignedPadCount: 0, bundleDigest: "a".repeat(64),
    }],
    importProject: unexpected("import"),
    createProject: unexpected("create"),
    duplicateProject: unexpected("duplicate"),
    openProject: async () => ({}),
    inspectProject: async () => ({
      project_revision: truth.revision,
      project: {
        contract: "lmdj.project.v5",
        project_id: PROJECT_ID,
        revision: truth.revision,
        bpm: 120,
        assets: {},
        banks: Array.from({length: 4}, (_, bank) => ({
          bank,
          pads: Array.from({length: 16}, (_, pad) => ({
            pad, asset_id: null, category: null, colour_override: null, colour: null,
          })),
        })),
        patterns: structuredClone(truth.patterns),
        pattern_slots: Array<string | null>(16).fill(null),
        sequence_settings: {quantize_enabled: true, swing_percent: 50},
      },
    }),
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false as const,
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: () => () => {},
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended", error_code: null, error_details: {},
      product_build: "9.8.7.6", host_id: "creator-web", host_version: "1.5.0",
      platform_version: "0.3.6", protocol_version: 1,
      capabilities: {
        secureContext: true, crossOriginIsolated: true, sharedArrayBuffer: true,
        webAssembly: true, audioWorklet: true, opfs: true,
        opfsSyncAccessHandle: true, opfsWritableReplace: true, webMidi: false,
      },
      trigger_admitted_count: 0, trigger_outcome_count: 0, trigger_rejected_count: 0,
    }),
    beginSequence: unexpected("begin"),
    flushSequence: unexpected("flush"),
    createPattern: unexpected("createPattern"),
    updateSequenceSettings: unexpected("settings"),
    editPatternEvents: unexpected("edit"),
    disarmSequenceCapture: async () => true,
    stopSequence: unexpected("stop"),
    requestPatternSwitch: unexpected("switch"),
    querySequenceStatus: sequenceStatus,
    listSequenceRecovery: async () => [],
    applySequenceRecovery: unexpected("recovery"),
    discardSequenceRecovery: async () => true,
    subscribeSequenceBarBoundary: () => () => true,
    resizePattern,
    doubleUpPattern: unexpected("doubleUpPattern"),
    copyPattern,
    requestPatternTransport: unexpected("transport"),
    inspectPatternTransport: async () => ({
      engaged: true, playing: false, recording: false, phase: "idle" as const,
      runtimeGeneration: 1, transportEpoch: 1, originFrame: 0, runtimeFrame: 0,
      observedAtMilliseconds: performance.now(), commandId: null,
      publicationPending: false, error: null,
    }),
  } as unknown as CreatorRuntimeSession;
  return {session, truth, resizePattern, copyPattern};
}

function failingReload(fixture: ReturnType<typeof structureFixture>) {
  const reloadSnapshot = vi.fn(async () => {
    throw Object.assign(new Error("publication still retiring"), {code: "HOST_STATE_INVALID"});
  });
  (fixture.session as unknown as {reloadSnapshot: unknown}).reloadSnapshot = reloadSnapshot;
  return reloadSnapshot;
}

async function openSetup(fixture: ReturnType<typeof structureFixture>) {
  render(<App runtimeFactory={() => fixture.session} />);
  await userEvent.click(await screen.findByRole("button", {name: "Open Project 11111111"}));
  await userEvent.click(await screen.findByRole("button", {name: "Sequence"}));
  await userEvent.click(await screen.findByRole("button", {name: "SETUP"}));
}

const pressed = (name: string) =>
  screen.getByRole("button", {name}).getAttribute("aria-pressed");

test("BARS resizes the selected Pattern at the authoring revision and reads the length back", async () => {
  const fixture = structureFixture();
  await openSetup(fixture);
  await waitFor(() => expect(pressed("Length 1 bars")).toBe("true"));
  await userEvent.click(screen.getByRole("button", {name: "Length 2 bars"}));
  await waitFor(() => expect(pressed("Length 2 bars")).toBe("true"));
  expect(fixture.resizePattern).toHaveBeenCalledExactlyOnceWith({
    patternId: PATTERN_ID, bars: 2, expectedRevision: 0,
  });
});

test("COPY copies the selected Pattern under a fresh id and selects the copy", async () => {
  const fixture = structureFixture();
  await openSetup(fixture);
  await userEvent.click(await screen.findByRole("button", {name: "Copy Pattern"}));
  await waitFor(() => expect(fixture.copyPattern).toHaveBeenCalledTimes(1));
  const request = fixture.copyPattern.mock.calls[0]![0];
  expect(request.sourcePatternId).toBe(PATTERN_ID);
  expect(request.expectedRevision).toBe(0);
  expect(request.patternId).toMatch(UUID);
  const stepper = screen.getByTestId("sequence-pattern");
  await waitFor(() =>
    expect(stepper.getAttribute("data-pattern-id")).toBe(request.patternId));
  expect(stepper.getAttribute("data-pattern-count")).toBe("2");
});

test("a committed copy is selected even when making it runtime-current fails", async () => {
  const fixture = structureFixture();
  await openSetup(fixture);
  const reloadSnapshot = failingReload(fixture);
  await userEvent.click(await screen.findByRole("button", {name: "Copy Pattern"}));
  await waitFor(() => expect(reloadSnapshot).toHaveBeenCalledTimes(1));
  const copyId = fixture.copyPattern.mock.calls[0]![0].patternId;
  const stepper = screen.getByTestId("sequence-pattern");
  await waitFor(() => expect(stepper.getAttribute("data-pattern-id")).toBe(copyId));
  expect(stepper.getAttribute("data-pattern-count")).toBe("2");
  // The reload failure is still reported, not swallowed.
  expect(await screen.findByRole("alert")).toBeTruthy();
});
