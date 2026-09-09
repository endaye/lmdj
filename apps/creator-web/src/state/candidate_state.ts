import type {CandidateJobView, CandidateSelection, CandidateSetView} from "../runtime/runtime_types";

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function invalid(): never {
  throw Object.assign(new Error("The Project source list could not be read. Refresh the Project."), {
    code: "HOST_PROTOCOL_MISMATCH",
  });
}
export interface CandidateSource {assetId: string; label: string}
// This is a projection of Facade inspection, never a Project bundle reader.
export function candidateSources(value: unknown, projectId: string): {
  revision: number; sources: CandidateSource[];
} {
  if (!record(value) || !record(value.project)) return invalid();
  const project = value.project;
  if (project.project_id !== projectId || !Number.isSafeInteger(project.revision) ||
      Number(project.revision) < 0 || project.revision !== value.project_revision ||
      !record(project.assets)) return invalid();
  const sources = Object.entries(project.assets).map(([assetId, asset], index) => {
    if (!uuid.test(assetId) || !record(asset) || !record(asset.artifact)) return invalid();
    const artifact = asset.artifact;
    if (typeof artifact.sha256 !== "string" || !/^[a-f0-9]{64}$/.test(artifact.sha256) ||
        typeof artifact.media_type !== "string" || !Number.isSafeInteger(artifact.byte_length) ||
        Number(artifact.byte_length) <= 0) return invalid();
    return {assetId, label: `Source ${index + 1} · ${assetId.slice(0, 8)}`};
  });
  return {revision: Number(project.revision), sources};
}
export function candidateJobId(projectId: string, assetId: string): string {
  if (!uuid.test(projectId) || !uuid.test(assetId)) return invalid();
  return `slice-${projectId}-${assetId}`;
}
export function activeCandidateSet(job: CandidateJobView | null): CandidateSetView | null {
  return job?.sets.find(set => set.set_id === job.active_set_id && set.status === "active") ?? null;
}
export interface CandidateTargetDraft {
  key: string; candidateId: string; bank: string; pad: string;
}
export function candidatePlan(rows: readonly CandidateTargetDraft[], set: CandidateSetView | null): {
  selections: CandidateSelection[]; error: string | null;
} {
  if (!set || rows.length === 0) return {selections: [], error: "Add a slice and choose its Bank and Pad."};
  const targets = new Set<string>();
  const selections: CandidateSelection[] = [];
  for (const row of rows) {
    if (!set.recipes.some(recipe => recipe.candidate_id === row.candidateId) ||
        !/^[0-3]$/.test(row.bank) || !/^(?:[0-9]|1[0-5])$/.test(row.pad)) {
      return {selections: [], error: "Choose a slice, Bank and Pad for every row."};
    }
    const target = `${row.bank}:${row.pad}`;
    if (targets.has(target)) return {selections: [], error: "Each target Pad can appear only once."};
    targets.add(target);
    selections.push({candidate_id: row.candidateId, bank: Number(row.bank), pad: Number(row.pad)});
  }
  return {selections, error: null};
}
