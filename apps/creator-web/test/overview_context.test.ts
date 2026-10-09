import {expect, test} from "vitest";
import {projectSamplePlayback} from "../src/state/sample_state";
import type {ProjectView} from "../src/runtime/runtime_types";
import {initialCreatorState, type CreatorState} from "../src/state/creator_state";
import {padContent, projectIdentity, projectStorageStatus, sampleIdentity} from "../src/state/overview_context";

const project: ProjectView = {
  projectId: "11111111-1111-4111-8111-111111111111",
  patternId: "22222222-2222-4222-8222-222222222222",
  revision: 3, bpm: 120, assetCount: 2, assignedPadCount: 2,
  bundleDigest: "a".repeat(64), key: "—",
  pads: Array.from({length: 64}, (_, slot) => ({slot,
    assetId: slot < 2 ? "33333333-3333-4333-8333-333333333333" : null,
    category: slot === 0 ? "bass" : null, colourOverride: null, colour: null})),
  patterns: [], patternSlots: Array<string | null>(16).fill(null),
  sequenceSettings: {quantizeEnabled: true, swingPercent: 50},
};
const ready: CreatorState = {...initialCreatorState,
  project: {...initialCreatorState.project, phase: "ready", current: project}};

test("identity uses the actual open Project and Pad address without inventing names", () => {
  expect(projectIdentity(project)).toBe("11111111");
  expect(projectIdentity(null)).toBe("NO PROJECT");
  expect(sampleIdentity(18)).toBe("PAD B03");
  expect(sampleIdentity(null)).toBe("NO PAD");
});

test("Pad role distinguishes assigned unknown category from empty and unavailable", () => {
  expect(padContent(project, 0)).toBe("BASS");
  expect(padContent(project, 1)).toBe("SAMPLE");
  expect(padContent(project, 2)).toBe("EMPTY");
  expect(padContent(null, 0)).toBe("UNAVAILABLE");
  expect(padContent(project, null)).toBe("NO PAD");
});

test("autosave policy is not presented as an aggregate saved receipt", () => {
  expect(projectStorageStatus(ready)).toBe("LOCAL AUTOSAVE");
  expect(projectStorageStatus(initialCreatorState)).toBe("NO PROJECT OPEN");
  expect(projectStorageStatus({...ready, project: {...ready.project, phase: "opening"}}))
    .toBe("OPENING");
  expect(projectStorageStatus({...ready, project: {...ready.project, phase: "error"}}))
    .toBe("NEEDS ATTENTION");
});

test("pending and failed Sample writes cannot look like a completed save", () => {
  expect(projectStorageStatus({...ready, sample: {...ready.sample,
    pendingAction: {kind: "update", slot: 0, expectedRevision: 3}}}))
    .toBe("UPDATING SAMPLE");
  expect(projectStorageStatus({...ready, sample: {...ready.sample,
    lastError: {code: "IO_ERROR", message: "Could not save", retryPrepare: false}}}))
    .toBe("SAMPLE NEEDS ATTENTION");
});

test("saved Sample Truth and prepared audio remain different states", () => {
  expect(projectStorageStatus({...ready, sample: {...ready.sample,
    savedRevision: 4, runtimeRevision: 3}})).toBe("SAMPLE SAVED · AUDIO PENDING");
  expect(projectStorageStatus({...ready, sample: {...ready.sample,
    savedRevision: 4, runtimeRevision: 4}})).toBe("LOCAL AUTOSAVE");
});


test("import, projection refresh and unsaved draft report their own pending state", () => {
  expect(projectStorageStatus({...ready, transfer: {...ready.transfer, phase: "importing"}}))
    .toBe("IMPORTING");
  expect(projectStorageStatus({...ready, projectProjectionRefresh: {id: "refresh-1",
    projectId: project.projectId, patternId: project.patternId, baseRevision: 3}}))
    .toBe("REFRESHING PROJECT");
  expect(projectStorageStatus({...ready, sample: {...ready.sample,
    draft: {baseRevision: 3, saved: projectSamplePlayback(undefined),
      proposed: {...projectSamplePlayback(undefined), gainMillidb: -6000}, dirty: true}}}))
    .toBe("UNSAVED SAMPLE EDIT");
});
