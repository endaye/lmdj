import {fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";

import {App} from "../src/app";
import type {CreatorRuntimeSession} from "../src/runtime/runtime_types";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const PATTERN_ID = "22222222-2222-4222-8222-222222222222";
const HISTORY_SESSION_ID = "20000000-0000-4000-8000-000000000001";

interface TruthEvent {
  slot: {bank: number; pad: number};
  onset_tick: number;
  duration_tick: number;
  velocity: number;
}

// A fake Host whose Project Truth is one Pattern's event list: the Session
// edit applies flat-slot remove/put by key, reports the publication the
// fixture is configured for, history replays the inverse, and every read
// (inspect, listing revision, transport inspection) derives from that Truth.
function gridFixture(options: {
  events?: TruthEvent[];
  playing?: boolean;
  publication?: "none" | "published" | "live" | "deferred" | "failed";
} = {}) {
  const truth = {
    revision: 0,
    events: [...(options.events ?? [])],
  };
  const playing = options.playing ?? false;
  const publication = options.publication ??
    (playing ? "live" : "published");
  const undoStack: {label: string; before: TruthEvent[]; after: TruthEvent[]}[] = [];
  const redoStack: {label: string; before: TruthEvent[]; after: TruthEvent[]}[] = [];
  const inspectProject = vi.fn(async () => ({
    project_revision: truth.revision,
    project: {
      contract: "lmdj.project.v5",
      project_id: PROJECT_ID,
      revision: truth.revision,
      bpm: 120,
      assets: {},
      banks: Array.from({length: 4}, (_, bank) => ({
        bank,
        pads: Array.from({length: 16}, (_, pad) => ({pad, asset_id: null})),
      })),
      patterns: {[PATTERN_ID]: {bars: 1, events: truth.events}},
      pattern_slots: Array<string | null>(16).fill(null),
      sequence_settings: {quantize_enabled: true, swing_percent: 50},
    },
  }));
  const editPatternEvents = vi.fn(async (request: {
    patternId: string;
    expectedRevision: number;
    remove: readonly {slot: number; onsetTick: number}[];
    put: readonly {slot: number; onsetTick: number;
      durationTick: number; velocity: number}[];
  }) => {
    const before = truth.events.map((event) => ({...event, slot: {...event.slot}}));
    const flat = (slot: {bank: number; pad: number}) => slot.bank * 16 + slot.pad;
    const kept = truth.events.filter((event) =>
      !request.remove.some((key) =>
        key.slot === flat(event.slot) && key.onsetTick === event.onset_tick));
    const merged = [
      ...kept.filter((event) =>
        !request.put.some((put) =>
          put.slot === flat(event.slot) && put.onsetTick === event.onset_tick)),
      ...request.put.map((put) => ({
        slot: {bank: Math.floor(put.slot / 16), pad: put.slot % 16},
        onset_tick: put.onsetTick,
        duration_tick: put.durationTick,
        velocity: put.velocity,
      })),
    ].sort((left, right) =>
      left.onset_tick - right.onset_tick ||
      flat(left.slot) - flat(right.slot));
    truth.events = merged;
    truth.revision += 1;
    undoStack.push({label: "Edit Pattern", before, after: merged});
    redoStack.length = 0;
    const swapped = publication === "published" || publication === "live";
    return {
      patternId: request.patternId,
      committedRevision: truth.revision,
      replayed: false,
      projectRevision: truth.revision,
      publication,
      patternPublication: swapped
        ? {generation: 2, activationFrame: 96_000}
        : null,
      snapshotError: publication === "failed"
        ? {code: "COOK_FAILED", message: "Audio unavailable", details: {}}
        : null,
    };
  });
  const transportStatus = () => ({
    engaged: true,
    playing,
    recording: false,
    phase: "idle" as const,
    runtimeGeneration: 1,
    transportEpoch: 1,
    originFrame: 96_000,
    runtimeFrame: 96_000,
    observedAtMilliseconds: performance.now(),
    commandId: null,
    publicationPending: false,
    error: null,
  });
  const session = {
    start: async () => true,
    close: async () => true,
    listLocalProjects: async () => [{
      projectId: PROJECT_ID,
      patternId: PATTERN_ID,
      revision: truth.revision,
      bpm: 120,
      assetCount: 0,
      assignedPadCount: 0,
      bundleDigest: "a".repeat(64),
    }],
    importProject: async () => { throw new Error("import is not expected"); },
    createProject: async () => { throw new Error("create is not expected"); },
    duplicateProject: async () => { throw new Error("duplicate is not expected"); },
    openProject: async () => ({}),
    inspectProject,
    reloadSnapshot: async () => ({}),
    activateAudio: async () => true,
    suspendAudio: async () => true,
    trigger: async () => false as const,
    requestMidi: async () => true,
    subscribeDiagnostics: () => () => {},
    subscribeHostState: () => () => {},
    subscribeRuntimeOutcome: () => () => {},
    diagnostics: () => ({
      state: "audio-suspended",
      error_code: null,
      error_details: {},
      product_build: "9.8.7.6",
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
    beginSequence: async () => { throw new Error("begin is not expected"); },
    flushSequence: async () => { throw new Error("flush is not expected"); },
    createPattern: async () => { throw new Error("createPattern is not expected"); },
    updateSequenceSettings: async () => { throw new Error("settings are not expected"); },
    editPatternEvents,
    disarmSequenceCapture: async () => true,
    stopSequence: async () => { throw new Error("stop is not expected"); },
    requestPatternSwitch: async () => { throw new Error("switch is not expected"); },
    querySequenceStatus: async () => ({
      state: "inactive" as const,
      sessionId: null,
      patternId: null,
      pendingPatternId: null,
      expectedRevision: truth.revision,
      nextFlushSequence: 1,
      pendingEventCount: 0,
      effectiveRuntimeFrame: null,
    }),
    listSequenceRecovery: async () => [],
    applySequenceRecovery: async () => { throw new Error("recovery is not expected"); },
    discardSequenceRecovery: async () => true,
    subscribeSequenceBarBoundary: () => () => true,
    requestPatternTransport: async () => { throw new Error("transport is not expected"); },
    inspectPatternTransport: async () => transportStatus(),
    inspectAuthoringHistory: async () => ({
      sessionId: HISTORY_SESSION_ID,
      projectRevision: truth.revision,
      undoCount: undoStack.length,
      redoCount: redoStack.length,
      undoLabel: undoStack.at(-1)?.label ?? "",
      redoLabel: redoStack.at(-1)?.label ?? "",
      disabledReason: "",
      canUndo: undoStack.length > 0,
      canRedo: redoStack.length > 0,
    }),
    undoAuthoring: async () => {
      const entry = undoStack.pop();
      if (entry === undefined) throw new Error("nothing to undo");
      truth.events = entry.before;
      truth.revision += 1;
      redoStack.push(entry);
      return {
        committedRevision: truth.revision,
        runtimeRevision: truth.revision,
        runtimePublished: true,
        snapshotError: null,
      };
    },
    redoAuthoring: async () => {
      const entry = redoStack.pop();
      if (entry === undefined) throw new Error("nothing to redo");
      truth.events = entry.after;
      truth.revision += 1;
      undoStack.push(entry);
      return {
        committedRevision: truth.revision,
        runtimeRevision: truth.revision,
        runtimePublished: true,
        snapshotError: null,
      };
    },
  } as unknown as CreatorRuntimeSession;
  return {session, truth, editPatternEvents, inspectProject};
}

// One bar is 3840 ticks over a 384 px lane; rows are 20 px lanes on a 22 px
// pitch inside the body.
function mockGridGeometry() {
  const body = document.querySelector(".sequence-grid-body") as HTMLElement;
  Object.defineProperty(body, "getBoundingClientRect", {
    configurable: true,
    value: () => ({left: 0, top: 0, width: 384, height: 352,
      right: 384, bottom: 352, x: 0, y: 0, toJSON: () => {}}),
  });
  document.querySelectorAll(".sequence-grid-lane").forEach((lane, index) => {
    Object.defineProperty(lane, "getBoundingClientRect", {
      configurable: true,
      value: () => ({left: 0, top: index * 22, width: 384, height: 20,
        right: 384, bottom: index * 22 + 20, x: 0, y: index * 22, toJSON: () => {}}),
    });
  });
}

const lane = (pad: number) =>
  document.querySelector(
    `.sequence-grid-row[data-pad="${pad}"] .sequence-grid-lane`) as HTMLElement;

async function openSequenceGrid(fixture: ReturnType<typeof gridFixture>) {
  render(<App runtimeFactory={() => fixture.session} />);
  await userEvent.click(
    await screen.findByRole("button", {name: "Open Project 11111111"}));
  await userEvent.click(
    await screen.findByRole("button", {name: "Sequence"}));
  await screen.findByTestId("sequence-grid");
  mockGridGeometry();
}

async function tapEmptyCell(pad: number, clientX: number, clientY: number) {
  fireEvent.pointerDown(lane(pad), {pointerId: 41, clientX, clientY, button: 0});
  fireEvent.pointerUp(window, {pointerId: 41});
}

const gridNote = () =>
  within(screen.getByTestId("sequence-grid")).queryByTestId("sequence-grid-note");

test("one gesture commits one flat-slot pattern events edit and both grids follow Truth", async () => {
  const fixture = gridFixture();
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  await waitFor(() => expect(fixture.editPatternEvents).toHaveBeenCalledTimes(1));
  expect(fixture.editPatternEvents).toHaveBeenCalledWith({
    patternId: PATTERN_ID,
    expectedRevision: 0,
    remove: [],
    put: [{slot: 2, onsetTick: 480, durationTick: 240, velocity: 100}],
  });
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"));
  await waitFor(() =>
    expect(screen.getByTestId("sequence-pattern-overview")
      .getElementsByClassName("sequence-overview-note")).toHaveLength(1));
});

test("a refused edit restores the projection from Truth and shows the reason", async () => {
  const fixture = gridFixture({events: [
    {slot: {bank: 0, pad: 1}, onset_tick: 240, duration_tick: 240, velocity: 100},
  ]});
  fixture.editPatternEvents.mockRejectedValueOnce(
    Object.assign(new Error("stale revision"), {code: "REVISION_CONFLICT"}));
  await openSequenceGrid(fixture);
  const inspectsBefore = fixture.inspectProject.mock.calls.length;
  const note = within(document.querySelector(
    ".sequence-grid-row[data-pad='1']") as HTMLElement)
    .getByTestId("sequence-grid-note");
  fireEvent.pointerDown(note, {pointerId: 42, clientX: 30, clientY: 32, button: 0});
  fireEvent.pointerUp(window, {pointerId: 42});
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent)
    .toContain("The Project changed while this was in progress.");
  // The projection was restored from Truth: the refused remove never shows,
  // and the note stays exactly as Project Truth holds it.
  expect(fixture.inspectProject.mock.calls.length).toBeGreaterThan(inspectsBefore);
  expect(within(document.querySelector(
    ".sequence-grid-row[data-pad='1']") as HTMLElement)
    .getByTestId("sequence-grid-note").getAttribute("data-onset-tick")).toBe("240");
  expect(fixture.truth.events).toHaveLength(1);
});

test("a transport-busy refusal is retried before commit and never shown as a conflict", async () => {
  const fixture = gridFixture();
  fixture.editPatternEvents.mockRejectedValueOnce(
    Object.assign(new Error("transport busy"), {
      code: "HOST_STATE_INVALID",
      details: {reason: "pattern_transport_busy"},
    }));
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"),
    {timeout: 10_000});
  expect(fixture.editPatternEvents).toHaveBeenCalledTimes(2);
  expect(fixture.editPatternEvents).toHaveBeenNthCalledWith(1, expect.objectContaining({
    put: [{slot: 2, onsetTick: 480, durationTick: 240, velocity: 100}],
  }));
  // Each attempt is a fresh command of the same gesture, named with the
  // current revision — deep-equal here because nothing intervened.
  expect(fixture.editPatternEvents.mock.calls[1]![0])
    .toEqual(fixture.editPatternEvents.mock.calls[0]![0]);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a busy retry re-reads authority after an intervening commit", async () => {
  const fixture = gridFixture();
  // The first attempt is refused pre-commit; the settling transport then lands
  // an intervening commit (revision 1) before the retry. The retry must name
  // the fresh revision, not the one frozen at gesture end.
  fixture.editPatternEvents.mockImplementationOnce(async () => {
    fixture.truth.revision = 1;
    throw Object.assign(new Error("transport busy"), {
      code: "HOST_STATE_INVALID",
      details: {reason: "pattern_transport_busy"},
    });
  });
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"),
    {timeout: 10_000});
  expect(fixture.editPatternEvents).toHaveBeenCalledTimes(2);
  expect(fixture.editPatternEvents.mock.calls[0]![0].expectedRevision).toBe(0);
  expect(fixture.editPatternEvents.mock.calls[1]![0].expectedRevision).toBe(1);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a busy retry that cannot re-read the revision surfaces the refusal, not a conflict", async () => {
  const fixture = gridFixture();
  // Refused pre-commit, then the revision re-read comes back unreadable: a
  // retry would name a known-stale revision, so the refusal stands.
  fixture.editPatternEvents.mockImplementationOnce(async () => {
    fixture.inspectProject.mockResolvedValueOnce({} as never);
    throw Object.assign(new Error("transport busy"), {
      code: "HOST_STATE_INVALID",
      details: {reason: "pattern_transport_busy"},
    });
  });
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  await screen.findByRole("alert", {}, {timeout: 10_000});
  expect(fixture.editPatternEvents).toHaveBeenCalledTimes(1);
  expect(screen.getByRole("alert").textContent).toContain("That can't be done right now.");
  expect(screen.getByRole("alert").textContent).not.toContain("Project changed");
  expect(fixture.truth.events).toHaveLength(0);
});

test("a live edit while playing swaps in place with no next-bar mark", async () => {
  const fixture = gridFixture({playing: true, publication: "live"});
  await openSequenceGrid(fixture);
  await tapEmptyCell(4, 60, 98);
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"));
  expect(screen.queryByText("applies from next bar")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a deferred edit is committed Truth like any other, with no separate state", async () => {
  const fixture = gridFixture({playing: true, publication: "deferred"});
  await openSequenceGrid(fixture);
  await tapEmptyCell(4, 60, 98);
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"));
  expect(fixture.truth.events).toHaveLength(1);
  expect(screen.queryByRole("alert")).toBeNull();
});

test("a committed edit whose swap fails surfaces the snapshot error honestly", async () => {
  const fixture = gridFixture({publication: "failed"});
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  await waitFor(() =>
    expect(gridNote()?.getAttribute("data-onset-tick")).toBe("480"));
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent)
    .toContain("A sound could not be prepared for playback. Your changes are saved.");
});

// Session history is the rail's SHIFT chord (#1770): SHIFT engages the layer,
// then ← / → are Undo/Redo. The lamp lights when the direction is available.
async function shiftAndPress(name: string) {
  await userEvent.click(
    screen.getByRole("button", {name: "SHIFT — engage the Undo/Redo layer"}));
  const key = screen.getByRole("button", {name});
  await waitFor(() => expect(key).toHaveProperty("disabled", false));
  await userEvent.click(key);
}

test("Undo and Redo refresh both grids from Truth", async () => {
  const fixture = gridFixture();
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  const grid = screen.getByTestId("sequence-grid");
  await waitFor(() =>
    expect(within(grid).getByTestId("sequence-grid-note")).toBeTruthy());
  await waitFor(() =>
    expect(screen.getByTestId("authoring-history-status").textContent)
      .toContain("Undo: Edit Pattern"));

  await shiftAndPress("Undo — SHIFT + ←");
  await waitFor(() =>
    expect(within(grid).queryByTestId("sequence-grid-note")).toBeNull());
  await waitFor(() =>
    expect(screen.getByTestId("sequence-pattern-overview")
      .getElementsByClassName("sequence-overview-note")).toHaveLength(0));
  expect(fixture.truth.events).toHaveLength(0);

  await waitFor(() =>
    expect(screen.getByTestId("authoring-history-status").textContent)
      .toContain("Redo: Edit Pattern"));
  await shiftAndPress("Redo — SHIFT + →");
  await waitFor(() =>
    expect(within(grid).getByTestId("sequence-grid-note")
      .getAttribute("data-onset-tick")).toBe("480"));
  await waitFor(() =>
    expect(screen.getByTestId("sequence-pattern-overview")
      .getElementsByClassName("sequence-overview-note")).toHaveLength(1));
  expect(fixture.truth.events).toHaveLength(1);
});

test("an Undo that removes a selected note drops it from the selection", async () => {
  const fixture = gridFixture();
  await openSequenceGrid(fixture);
  await tapEmptyCell(2, 60, 54);
  const grid = screen.getByTestId("sequence-grid");
  await waitFor(() =>
    expect(within(grid).getByTestId("sequence-grid-note")).toBeTruthy());
  mockGridGeometry();
  // Box-select the note at tick 480 (48 px) on pad 2.
  fireEvent.pointerDown(lane(2), {pointerId: 43, clientX: 40, clientY: 50, button: 0});
  fireEvent.pointerMove(lane(2), {pointerId: 43, clientX: 100, clientY: 60});
  fireEvent.pointerUp(window, {pointerId: 43});
  const overview = () => screen.getByTestId("sequence-overview");
  const fact = (name: string) =>
    within(overview()).getByText(name).nextElementSibling?.textContent;
  await waitFor(() => expect(fact("Selected")).toBe("1"));

  await shiftAndPress("Undo — SHIFT + ←");
  await waitFor(() =>
    expect(within(grid).queryByTestId("sequence-grid-note")).toBeNull());
  // An empty selection drops the Selected fact from the context line.
  await waitFor(() => expect(within(overview()).queryByText("Selected")).toBeNull());
});
