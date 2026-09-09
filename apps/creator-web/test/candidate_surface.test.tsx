import {act, fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {expect, test, vi} from "vitest";
import {CandidateSurface, isCandidateSession} from "../src/components/candidate_surface";
import type {CandidateJobView, CreatorCandidateRuntimeSession} from "../src/runtime/runtime_types";
const projectId = "11111111-1111-4111-8111-111111111111";
const assetId = "22222222-2222-4222-8222-222222222222";
const otherId = "33333333-3333-4333-8333-333333333333";
const jobId = `slice-${projectId}-${assetId}`;
function job(empty = false): CandidateJobView {return {job_id: jobId, active_set_id: "set", history: [],
  sets: [{set_id: "set", status: "active", attempt_id: "attempt",
    source: {project_id: projectId, asset_id: assetId, project_revision: 3},
    recipes: empty ? [] : [{candidate_id: "recipe", kind: "slice_interval_v1", start_frame: 0, end_frame: 48000, frame_rate: 48000}]}]};}
function setup(options: {missing?: boolean; empty?: boolean} = {}) {
  const truth = {project_revision: 3, project: {project_id: projectId, revision: 3,
    assets: Object.fromEntries([assetId, otherId].map(id => [id, {artifact: {sha256: "a".repeat(64), media_type: "audio/wav", byte_length: 96044}}])),
    patterns: {pattern: {events: [{slot: {bank: 0, pad: 0}, tick: 0}]}}, banks: []}};
  let grants = ["other.permission"];
  const session = {
    inspectProject: vi.fn(async () => structuredClone(truth)),
    listProviders: vi.fn(async () => ({granted_permissions: grants,
      providers: [{id: "local.sample.slice", capabilities: [{capability_id: "sample.slice.v1"}]}]})),
    configureProviderPermissions: vi.fn(async (permissions: readonly string[]) => {
      grants = [...permissions]; return {granted_permissions: grants};
    }),
    selectProvider: vi.fn(async () => ({})),
    inspectCandidateJob: vi.fn(async () => {if (options.missing) throw {code: "NOT_FOUND"}; return job(options.empty);}),
    runCandidateJob: vi.fn(async () => job(options.empty)),
    cancelCandidateJob: vi.fn(async () => job()),
    discardCandidateSet: vi.fn(async () => ({...job(), active_set_id: null})),
    auditionCandidate: vi.fn(async () => ({played: true, project_revision: 3})),
    stopCandidateAudition: vi.fn(async () => ({})),
    adoptCandidates: vi.fn(async () => ({project_revision: 4, set_id: "set", adopted: [{candidate_id: "recipe", bank: 0, pad: 1, asset_id: otherId}]})),
  };
  const refresh = vi.fn(async () => {});
  const view = render(<CandidateSurface session={session as unknown as CreatorCandidateRuntimeSession}
    projectId={projectId} projectRevision={3} onRefreshProject={refresh} />);
  return {session, refresh, truth, ...view};
}
async function source() {
  await screen.findByRole("option", {name: /Source 1/});
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice source"}), assetId);
  await waitFor(() => expect(screen.getByRole("button", {name: "Refresh slices and Project"}).hasAttribute("disabled")).toBe(false));
}
async function target(index: number, pad: string) {
  await userEvent.click(screen.getByRole("button", {name: "Add target"}));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: `Target ${index} slice`}), "recipe");
  await userEvent.selectOptions(screen.getByRole("combobox", {name: `Target ${index} Bank`}), "0");
  await userEvent.selectOptions(screen.getByRole("combobox", {name: `Target ${index} Pad`}), screen.getByRole("combobox", {name: `Target ${index} Pad`}).querySelector(`option[value="${pad}"]`)!);
}
test("optional session guard leaves base Host mocks unchanged", () => {
  expect(isCandidateSession(undefined)).toBe(false);
  expect(isCandidateSession({} as CreatorCandidateRuntimeSession)).toBe(false);
});
test("analysis requires explicit Provider and permission, preserves other grants and uses a fresh Attempt", async () => {
  const {session} = setup({missing: true}); await source();
  expect(session.selectProvider).not.toHaveBeenCalled(); expect(session.configureProviderPermissions).not.toHaveBeenCalled();
  expect(screen.getByRole("button", {name: "Analyze"}).hasAttribute("disabled")).toBe(true);
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice Provider"}), "local.sample.slice");
  await userEvent.click(screen.getByRole("button", {name: "Grant analysis permission"}));
  await screen.findByRole("button", {name: "Analysis permission granted"});
  expect(screen.getByRole("button", {name: "Analyze"}).hasAttribute("disabled")).toBe(true);
  await userEvent.click(screen.getByRole("checkbox", {name: "Use this source as public audio for local analysis"}));
  expect(session.configureProviderPermissions).toHaveBeenCalledWith(["other.permission", "sample.slice.execute"]);
  await userEvent.click(screen.getByRole("button", {name: "Analyze"}));
  await screen.findByRole("button", {name: "Retry analysis"});
  await userEvent.click(screen.getByRole("button", {name: "Retry analysis"}));
  expect(session.runCandidateJob).toHaveBeenCalledTimes(2);
  const calls = session.runCandidateJob.mock.calls as unknown as [{[key: string]: unknown}][];
  expect(calls[0]![0]).toMatchObject({job_id: jobId, project_id: projectId, asset_id: assetId, expected_revision: 3, data_classification: "public", platform: "test"});
  expect(calls[0]![0].attempt_id).not.toBe(calls[1]![0].attempt_id);
});
test("successful no-onset is visible and has no adoption targets", async () => {
  setup({empty: true}); await source();
  expect(await screen.findByText("Analysis complete. No slices detected.")).toBeTruthy();
  expect(screen.queryByRole("button", {name: "Add target"})).toBeNull();
});
test("targets start blank and duplicate Pad refuses, while repeated recipe to two Pads commits once", async () => {
  const {session, refresh} = setup(); await source();
  await userEvent.click(screen.getByRole("button", {name: "Add target"}));
  for (const name of ["slice", "Bank", "Pad"]) expect((screen.getByRole("combobox", {name: `Target 1 ${name}`}) as HTMLSelectElement).value).toBe("");
  await userEvent.click(screen.getByRole("button", {name: "Remove target 1"}));
  await target(1, "1"); await target(2, "1");
  expect(screen.getByText("Each target Pad can appear only once.")).toBeTruthy();
  expect(screen.getByRole("button", {name: "Adopt selected slices"}).hasAttribute("disabled")).toBe(true);
  expect(session.adoptCandidates).not.toHaveBeenCalled();
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Target 2 Pad"}), screen.getByRole("combobox", {name: "Target 2 Pad"}).querySelector('option[value="2"]')!);
  fireEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  fireEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await waitFor(() => expect(session.adoptCandidates).toHaveBeenCalledTimes(1));
  expect(session.adoptCandidates).toHaveBeenCalledWith(expect.objectContaining({expected_revision: 3,
    selections: [{candidate_id: "recipe", bank: 0, pad: 1}, {candidate_id: "recipe", bank: 0, pad: 2}]}));
  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
});
test("played false is honest, stop and teardown change no Project truth", async () => {
  const {session, truth, unmount} = setup(); const before = structuredClone(truth);
  session.auditionCandidate.mockResolvedValue({played: false, project_revision: 3});
  await source(); await userEvent.click(screen.getByRole("button", {name: "Preview slice 1"}));
  expect(await screen.findByText("Preview was not played. Activate audio and try again.")).toBeTruthy();
  await userEvent.click(screen.getByRole("button", {name: "Stop preview"}));
  await screen.findByText("Preview stopped.");
  const count = session.stopCandidateAudition.mock.calls.length; unmount();
  expect(session.stopCandidateAudition.mock.calls.length).toBe(count + 1);
  expect(truth).toEqual(before); expect(session.adoptCandidates).not.toHaveBeenCalled();
});
test("late preview response after a source switch is stopped and never shown", async () => {
  const {session} = setup(); await source();
  let resolve!: (value: {played: boolean; project_revision: number}) => void;
  session.auditionCandidate.mockImplementation(() => new Promise(done => {resolve = done;}));
  await userEvent.click(screen.getByRole("button", {name: "Preview slice 1"}));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice source"}), otherId);
  const count = session.stopCandidateAudition.mock.calls.length;
  await act(async () => {resolve({played: true, project_revision: 3});});
  expect(session.stopCandidateAudition.mock.calls.length).toBe(count + 1);
  expect(screen.queryByText("Preview started.")).toBeNull();
});
test.each(["REVISION_CONFLICT", "NOT_FOUND", "RESOURCE_EXHAUSTED", "HOST_TIMEOUT"])("%s adoption leaves truth unchanged and requires inspection before another command", async code => {
  const {session, truth, refresh} = setup(); const before = structuredClone(truth);
  session.adoptCandidates.mockRejectedValue({code});
  await source(); await target(1, "1"); await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await screen.findByText(/previous request may have committed/);
  expect(truth).toEqual(before); expect(session.adoptCandidates).toHaveBeenCalledTimes(1);
  expect(refresh).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Refresh slices and Project"}));
  await waitFor(() => expect(screen.queryByText(/previous request may have committed/)).toBeNull());
  expect(refresh).toHaveBeenCalledTimes(1); expect(session.adoptCandidates).toHaveBeenCalledTimes(1);
});
test("discard removes active recipes without an adoption", async () => {
  const {session, truth} = setup(); const before = structuredClone(truth); await source();
  await userEvent.click(screen.getByRole("button", {name: "Discard slices"}));
  expect(await screen.findByText("No active slices. Retry analysis to create a new result.")).toBeTruthy();
  expect(truth).toEqual(before); expect(session.adoptCandidates).not.toHaveBeenCalled();
});

test("a late analysis result cannot repopulate the newly selected source", async () => {
  const {session} = setup({missing: true}); await source();
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice Provider"}), "local.sample.slice");
  await userEvent.click(screen.getByRole("button", {name: "Grant analysis permission"}));
  await screen.findByRole("button", {name: "Analysis permission granted"});
  expect(screen.getByRole("button", {name: "Analyze"}).hasAttribute("disabled")).toBe(true);
  await userEvent.click(screen.getByRole("checkbox", {name: "Use this source as public audio for local analysis"}));
  let finish!: (value: CandidateJobView) => void;
  session.runCandidateJob.mockImplementation(() => new Promise(resolve => {finish = resolve;}));
  await userEvent.click(screen.getByRole("button", {name: "Analyze"}));
  await waitFor(() => expect(session.runCandidateJob).toHaveBeenCalledTimes(1));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice source"}), otherId);
  await act(async () => {finish(job());});
  expect(screen.queryByRole("heading", {name: "Detected slices"})).toBeNull();
  expect(session.stopCandidateAudition).toHaveBeenCalled();
  expect(session.adoptCandidates).not.toHaveBeenCalled();
});
test("page teardown stops audition without an authoring command", async () => {
  const {session} = setup(); await source();
  const count = session.stopCandidateAudition.mock.calls.length;
  fireEvent(window, new Event("pagehide"));
  expect(session.stopCandidateAudition.mock.calls.length).toBe(count + 1);
  expect(session.adoptCandidates).not.toHaveBeenCalled();
});
test("a committed adoption with failed projection remains blocked until successful inspection", async () => {
  const {session, refresh} = setup(); await source(); await target(1, "1");
  refresh.mockRejectedValueOnce(new Error("Project refresh failed"));
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await screen.findByText(/previous request may have committed/);
  expect(session.adoptCandidates).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("button", {name: "Refresh slices and Project"}));
  await waitFor(() => expect(screen.queryByText(/previous request may have committed/)).toBeNull());
  expect(refresh).toHaveBeenCalledTimes(2);
  expect(session.adoptCandidates).toHaveBeenCalledTimes(1);
});

test("pending adoption keeps uncertainty across source switches until Project inspection", async () => {
  const {session, refresh} = setup(); await source(); await target(1, "1");
  let reject!: (error: unknown) => void;
  session.adoptCandidates.mockImplementation(() => new Promise((_resolve, failed) => {reject = failed;}));
  await userEvent.click(screen.getByRole("button", {name: "Adopt selected slices"}));
  await waitFor(() => expect(session.adoptCandidates).toHaveBeenCalledTimes(1));
  await userEvent.selectOptions(screen.getByRole("combobox", {name: "Slice source"}), otherId);
  await screen.findByText(/previous request may have committed/);
  expect(screen.getByRole("button", {name: "Add target"}).closest("fieldset")?.disabled).toBe(true);
  expect(screen.getByRole("button", {name: "Refresh slices and Project"}).hasAttribute("disabled")).toBe(true);
  await act(async () => {reject({code: "HOST_TIMEOUT"});});
  expect(screen.getByText(/previous request may have committed/)).toBeTruthy();
  expect(refresh).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", {name: "Refresh slices and Project"}));
  await waitFor(() => expect(screen.queryByText(/previous request may have committed/)).toBeNull());
  expect(session.adoptCandidates).toHaveBeenCalledTimes(1);
});
