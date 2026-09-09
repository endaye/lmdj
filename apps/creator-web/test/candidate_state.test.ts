import {expect, test} from "vitest";
import {candidateJobId, candidateSources, candidatePlan} from "../src/state/candidate_state";
import type {CandidateSetView} from "../src/runtime/runtime_types";
const projectId = "11111111-1111-4111-8111-111111111111";
const assetId = "22222222-2222-4222-8222-222222222222";
const set: CandidateSetView = {set_id: "set", status: "active", attempt_id: "attempt",
  source: {project_id: projectId, asset_id: assetId, project_revision: 3},
  recipes: [{candidate_id: "recipe", kind: "slice_interval_v1", start_frame: 0, end_frame: 400, frame_rate: 48000}]};
function inspection() {return {project_revision: 3, project: {project_id: projectId, revision: 3,
  assets: {[assetId]: {artifact: {sha256: "a".repeat(64), media_type: "audio/wav", byte_length: 100}}}}};}
test("source projection retains an unassigned Asset and stable reload Job identity", () => {
  expect(candidateSources(inspection(), projectId).sources.map(item => item.assetId)).toEqual([assetId]);
  expect(candidateJobId(projectId, assetId)).toBe(`slice-${projectId}-${assetId}`);
  expect(candidateJobId(projectId, assetId).length).toBeLessThanOrEqual(128);
});
test("source projection rejects mismatched Project revision or malformed Artifact", () => {
  const value = inspection(); value.project.revision = 4;
  expect(() => candidateSources(value, projectId)).toThrow();
  const damaged = inspection(); damaged.project.assets[assetId]!.artifact.sha256 = "bad";
  expect(() => candidateSources(damaged, projectId)).toThrow();
  expect(() => candidateSources(inspection(), assetId)).toThrow();
});
test("an explicit plan rejects missing and duplicate Pads without inventing targets", () => {
  expect(candidatePlan([{key: "1", candidateId: "recipe", bank: "", pad: ""}], set).selections).toEqual([]);
  const row = {key: "1", candidateId: "recipe", bank: "0", pad: "1"};
  expect(candidatePlan([row, {...row, key: "2"}], set).error).toContain("only once");
});
test("the same recipe can explicitly target separate Pads", () => {
  const row = {key: "1", candidateId: "recipe", bank: "0", pad: "1"};
  expect(candidatePlan([row, {...row, key: "2", pad: "2"}], set)).toEqual({error: null,
    selections: [{candidate_id: "recipe", bank: 0, pad: 1}, {candidate_id: "recipe", bank: 0, pad: 2}]});
});
