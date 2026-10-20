import {act, fireEvent, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {SampleSurface} from "../src/components/sample_surface";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {preparedSampleState, selectSampleSlot} from "../src/state/sample_state";
import type {CreatorPadAssignmentRuntimeSession, CreatorSampleRuntimeSession, PadAssignmentRequest} from "../src/runtime/runtime_types";

const projectId = "11111111-1111-4111-8111-111111111111";
const asset = "33333333-3333-4333-8333-333333333333";
const unassigned = "44444444-4444-4444-8444-444444444444";
const other = "55555555-5555-4555-8555-555555555555";
function catalog(revision = 4) {
  return {project_revision: revision, project: {project_id: projectId, revision,
    assets: Object.fromEntries([asset, unassigned, other].map(id => [id, {artifact: {
      sha256: "a".repeat(64), media_type: "audio/wav", byte_length: 60,
    }}]))}};
}
function fixture() {
  const state: CreatorState = {...initialCreatorState,
    runtime: {phase: "ready", errorCode: null},
    sample: selectSampleSlot(preparedSampleState(4), 0),
    project: {phase: "ready", projects: [], current: {projectId,
      patternId: "22222222-2222-4222-8222-222222222222", revision: 4, bpm: 120,
      assetCount: 3, assignedPadCount: 2, bundleDigest: "b".repeat(64), key: "—",
      pads: Array.from({length: 64}, (_, slot) => ({slot,
        assetId: slot === 0 ? asset : slot === 1 ? other : null,
        category: null, colour: null, colourOverride: null})),
      patterns: [], patternSlots: Array(16).fill(null),
      sequenceSettings: {quantizeEnabled: true, swingPercent: 50}}}};
  const session = {inspectProject: vi.fn(async () => catalog()),
    inspectSample: vi.fn(async (slot: number) => ({projectRevision: 4, slot,
      assetId: null, metadata: null, waveformCacheIdentity: null,
      playback: {trimStartFrame: 0, trimEndFrame: null, triggerMode: "one_shot",
        gainMillidb: 0, muted: false, reverse: false, pitchCents: 0, pan: 0,
        loopMode: "forward", loopStartFrame: null, loopCrossfadeFrames: 0,
        attackMs: 0, releaseMs: 0, tone: 0, eq: {low: null, mid: null, high: null}}})),
    stopPad: vi.fn(), stopAll: vi.fn(), trigger: vi.fn(), assignPad: vi.fn(),
    clearSamplePreview: vi.fn(),
  } as unknown as CreatorSampleRuntimeSession & CreatorPadAssignmentRuntimeSession;
  const onAssign = vi.fn(async (_request: Readonly<PadAssignmentRequest>) => {});
  const props = {state, session, assignment: {session, busy: false, onAssign},
    dispatch: vi.fn(), filePickIntent: {current: (_slot: number) => {}}};
  return {...render(<SampleSurface {...props} />), props, state, session, onAssign};
}
// Let the awaited read/React chain reach its far side before asserting absence.
async function settle() {await act(async () => {await new Promise(resolve => setTimeout(resolve, 0));});}
async function choose(source = unassigned, slot = "63") {
  await userEvent.click(screen.getByRole("button", {name: "ASSIGN"}));
  await waitFor(() => expect(screen.getByRole("combobox", {name: "Retained source"})).toHaveProperty("disabled", false));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Retained source"}), source);
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Destination Pad"}), slot);
}

test("projects every retained source including unassigned and independently enumerates A01–D16", async () => {
  const view = fixture();
  const before = JSON.stringify(view.state);
  await choose();
  const source = screen.getByRole("combobox", {name: "Retained source"});
  expect(Array.from(source.querySelectorAll("option"), option => option.value)).toEqual(["", asset, unassigned, other]);
  const options = within(screen.getByRole("combobox", {name: "Destination Pad"})).getAllByRole("option");
  // Independent closed-form oracle: the UI uses view_model labels, these
  // expectations use four explicit bank names and 1-based Pad numbers.
  expect(options.map(option => [option.getAttribute("value"), option.textContent])).toEqual(
    ["A", "B", "C", "D"].flatMap((bank, bankIndex) => Array.from({length: 16}, (_, pad) =>
      [String(bankIndex * 16 + pad), `${bank}${String(pad + 1).padStart(2, "0")}`])));
  expect(options.filter(option => ["A01", "A16", "B01", "C16", "D16"].includes(option.textContent!))).toHaveLength(5);
  await settle();
  expect(view.onAssign).not.toHaveBeenCalled();
  expect(view.session.trigger).not.toHaveBeenCalled();
  expect(view.session.stopPad).not.toHaveBeenCalled();
  expect(JSON.stringify(view.state)).toBe(before);
});

test("held initial catalog keeps its only read when loading destination change is attempted", async () => {
  const view = fixture();
  let finish!: (value: unknown) => void;
  vi.mocked(view.session.inspectProject).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
  await userEvent.click(screen.getByRole("button", {name: "ASSIGN"}));
  const destination = screen.getByRole("combobox", {name: "Destination Pad"});
  expect(destination).toHaveProperty("disabled", true);
  expect(screen.getByRole("combobox", {name: "Retained source"})).toHaveProperty("disabled", true);
  // Also guard a forced handler event on the disabled loading control. The
  // only catalog reply must still belong to the initial draft afterward.
  fireEvent.change(destination, {target: {value: "63"}});
  await act(async () => {finish(catalog());});
  await waitFor(() => expect(screen.getByRole("combobox", {name: "Retained source"})).toHaveProperty("disabled", false));
  expect(destination).toHaveProperty("disabled", false);
  expect(destination).toHaveProperty("value", "0");
  expect(within(destination).getAllByRole("option")).toHaveLength(64);
  expect(Array.from(screen.getByRole("combobox", {name: "Retained source"}).querySelectorAll("option"),
    option => option.value)).toEqual(["", asset, unassigned, other]);
  expect(view.session.inspectProject).toHaveBeenCalledTimes(1);
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Retained source"}), unassigned);
  await userEvent.selectOptions(destination, "63");
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  await waitFor(() => expect(view.onAssign).toHaveBeenCalledTimes(1));
  expect(view.onAssign.mock.calls[0]![0]).toMatchObject({assetId: unassigned, slot: 63});
});

test("empty destination invokes one frozen four-field request after a fresh catalog read", async () => {
  const view = fixture();
  await choose();
  const submit = screen.getByRole("button", {name: "Assign Asset"});
  await userEvent.dblClick(submit);
  await waitFor(() => expect(view.onAssign).toHaveBeenCalledTimes(1));
  const request = view.onAssign.mock.calls[0]![0];
  expect(request).toEqual({commandId: expect.any(String), expectedRevision: 4, slot: 63, assetId: unassigned});
  expect(Object.isFrozen(request)).toBe(true);
  expect(view.session.inspectProject).toHaveBeenCalledTimes(2);
  expect(view.session.stopPad).not.toHaveBeenCalled();
  expect(view.session.trigger).not.toHaveBeenCalled();
});

test("fresh-session reconfirmation starts without a destination and requires one new explicit choice", async () => {
  const view = fixture();
  view.rerender(<SampleSurface {...view.props}
    assignment={{...view.props.assignment, reconfirmationRequired: true}} />);
  await userEvent.click(screen.getByRole("button", {name: "ASSIGN"}));
  const source = screen.getByRole("combobox", {name: "Retained source"});
  const destination = screen.getByRole("combobox", {name: "Destination Pad"});
  await waitFor(() => expect(source).toHaveProperty("disabled", false));
  expect(destination).toHaveProperty("value", "");
  await userEvent.selectOptions(source, unassigned);
  const submit = screen.getByRole("button", {name: "Assign Asset"});
  expect(submit).toHaveProperty("disabled", true);
  fireEvent.click(submit);
  await settle();
  expect(view.onAssign).not.toHaveBeenCalled();
  await userEvent.selectOptions(destination, "63");
  const confirmed = screen.getByRole("button", {name: "Assign Asset"});
  expect(confirmed).toHaveProperty("disabled", false);
  await userEvent.click(confirmed);
  await waitFor(() => expect(view.onAssign).toHaveBeenCalledTimes(1));
  expect(view.onAssign.mock.calls[0]![0]).toMatchObject({assetId: unassigned, slot: 63});
});

test.each(["Cancel", "Escape"])("occupied %s never invokes, stops or changes Truth", async action => {
  const view = fixture();
  const before = JSON.stringify(view.state);
  await choose(unassigned, "1");
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  await screen.findByRole("button", {name: "Confirm replacement"});
  expect(screen.getByRole("dialog").textContent).toContain(`${unassigned} → A02`);
  expect(screen.getByRole("dialog").textContent).toContain(other);
  if (action === "Escape") await userEvent.keyboard("{Escape}");
  else await userEvent.click(screen.getByRole("button", {name: "Cancel assignment"}));
  await settle();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(view.onAssign).not.toHaveBeenCalled();
  expect(view.session.stopPad).not.toHaveBeenCalled();
  expect(view.session.trigger).not.toHaveBeenCalled();
  expect(JSON.stringify(view.state)).toBe(before);
});

test("affirmative overwrite revalidates and sends the selected target exactly once", async () => {
  const view = fixture();
  await choose(unassigned, "1");
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  await userEvent.click(await screen.findByRole("button", {name: "Confirm replacement"}));
  await waitFor(() => expect(view.onAssign).toHaveBeenCalledTimes(1));
  expect(view.onAssign).toHaveBeenCalledWith({commandId: expect.any(String), expectedRevision: 4,
    slot: 1, assetId: unassigned});
  expect(view.session.inspectProject).toHaveBeenCalledTimes(3);
});

test.each(["Pad", "Project", "session"])("occupied confirmation loses %s context without invoking", async loss => {
  const view = fixture();
  await choose(unassigned, "1");
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  const retired = await screen.findByRole("button", {name: "Confirm replacement"});
  const state = loss === "Pad" ? {...view.state, sample: selectSampleSlot(view.state.sample, 2)}
    : loss === "Project" ? {...view.state, project: {...view.state.project,
      current: {...view.state.project.current!, projectId: other}}} : view.state;
  const session = loss === "session" ? {...view.session} : view.session;
  view.rerender(<SampleSurface {...view.props} state={state} session={session}
    assignment={{...view.props.assignment, session}} />);
  fireEvent.click(retired);
  await settle();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(view.onAssign).not.toHaveBeenCalled();
  expect(view.session.stopPad).not.toHaveBeenCalled();
  expect(view.session.trigger).not.toHaveBeenCalled();
});

test("destination change retires old affirmative confirmation before its queued click", async () => {
  const view = fixture();
  await choose(unassigned, "1");
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  const oldConfirm = await screen.findByRole("button", {name: "Confirm replacement"});
  fireEvent.change(screen.getByRole("combobox", {name: "Destination Pad"}), {target: {value: "63"}});
  fireEvent.click(oldConfirm);
  await settle();
  expect(view.onAssign).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", {name: "Confirm replacement"})).toBeNull();
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  await waitFor(() => expect(view.onAssign).toHaveBeenCalledTimes(1));
  expect(view.onAssign.mock.calls[0]![0]).toMatchObject({slot: 63});
});

test.each(["revision", "missing", "artifact"])("%s catalog refuses confirmation without invoking", async loss => {
  const view = fixture();
  await choose();
  const value = catalog(loss === "revision" ? 5 : 4);
  if (loss === "missing") delete value.project.assets[unassigned];
  if (loss === "artifact") value.project.assets[unassigned]!.artifact.byte_length = 0;
  vi.mocked(view.session.inspectProject).mockResolvedValue(value);
  await userEvent.click(screen.getByRole("button", {name: "Assign Asset"}));
  await screen.findByRole("alert");
  await settle();
  expect(view.onAssign).not.toHaveBeenCalled();
  expect(view.session.stopPad).not.toHaveBeenCalled();
});

test.each(["Escape", "Pad", "Project", "session", "hidden"])(
  "held catalog completion after %s cannot populate a replacement picker", async loss => {
    const view = fixture();
    let finish!: (value: unknown) => void;
    vi.mocked(view.session.inspectProject).mockImplementationOnce(() => new Promise(resolve => {finish = resolve;}));
    await userEvent.click(screen.getByRole("button", {name: "ASSIGN"}));
    if (loss === "Escape") {
      expect(document.activeElement).toBe(screen.getByRole("button", {name: "Cancel assignment"}));
      await userEvent.keyboard("{Escape}");
    }
    else {
      const state = loss === "Pad" ? {...view.state, sample: selectSampleSlot(view.state.sample, 2)}
        : loss === "Project" ? {...view.state, project: {...view.state.project,
          current: {...view.state.project.current!, projectId: other}}} : view.state;
      const session = loss === "session" ? {...view.session} : view.session;
      view.rerender(<SampleSurface {...view.props} state={state} session={session}
        assignment={{...view.props.assignment, session}} encodersActive={loss !== "hidden"} />);
    }
    await act(async () => {finish(catalog());});
    await settle();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(view.onAssign).not.toHaveBeenCalled();
    expect(view.session.stopPad).not.toHaveBeenCalled();
  });
