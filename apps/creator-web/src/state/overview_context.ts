import type {CreatorState} from "./creator_state";
import type {ProjectView} from "../runtime/runtime_types";
import {shortProjectId, slotAddress} from "./view_model";

// Public projections have no Project/Asset display name. Never infer one from
// an ID, colour override, waveform or a design's example data.
export function projectIdentity(project: ProjectView | null): string {
  return project === null ? "NO PROJECT" : shortProjectId(project.projectId);
}

export function padContent(project: ProjectView | null, slot: number | null): string {
  if (slot === null) return "NO PAD";
  const pad = project?.pads.find(value => value.slot === slot);
  if (pad === undefined) return "UNAVAILABLE";
  if (pad.assetId === null) return "EMPTY";
  return pad.category?.toUpperCase() ?? "SAMPLE";
}

export function sampleIdentity(slot: number | null): string {
  return slot === null ? "NO PAD" : `PAD ${slotAddress(slot)}`;
}

// This is the observable local state, not an invented aggregate save receipt
// or timestamp. A loaded Project's autosave policy does not prove that every
// independent recording/draft is already committed.
export function projectStorageStatus(state: CreatorState): string {
  if (state.transfer.phase === "importing") return "IMPORTING";
  if (state.project.phase === "opening") return "OPENING";
  if (state.project.phase === "error") return "NEEDS ATTENTION";
  if (state.project.current === null) return "NO PROJECT OPEN";
  if (state.sample.pendingAction !== null) return "UPDATING SAMPLE";
  if (state.projectProjectionRefresh !== null || state.sampleProjectionRefresh !== null) return "REFRESHING PROJECT";
  if (state.sample.savedRevision !== null && state.sample.savedRevision !== state.sample.runtimeRevision) {
    return "SAMPLE SAVED · AUDIO PENDING";
  }
  // A failed audio publication does not undo the committed Sample.
  if (state.sample.lastError !== null) return "SAMPLE NEEDS ATTENTION";
  if (state.sample.draft?.dirty) return "UNSAVED SAMPLE EDIT";
  return "LOCAL AUTOSAVE";
}
