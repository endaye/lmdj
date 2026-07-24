import { padElementIds, type Patch, type PatchBundle } from "../../patch/loader";

export type WorkbenchMode = "source" | "performance" | "export";

export type WorkbenchReadiness = "ready" | "needs-review" | "partial";

export interface WorkbenchExportState {
  status: "unknown" | "complete" | "partial";
  missing: string[];
  key: string | null;
}

export interface WorkbenchViewModel {
  patchId: string;
  schema: Patch["schema"];
  bpm: number;
  key: string | null;
  durationSeconds: number;
  padCount: 16;
  selectedPad?: Patch["pads"][number];
  selectedPadSources: WorkbenchElementSummary[];
  elements: WorkbenchElementSummary[];
  quality: {
    status: string;
    score: number | string | null;
  };
  unmappedElementIds: string[];
  warnings: string[];
  readiness: WorkbenchReadiness;
  blockers: string[];
}

export interface WorkbenchElementSummary {
  elementId: string;
  name: string;
  kind: string;
  sourcePath: string | null;
  status: "ready" | "missing" | "unavailable";
}

const DEFAULT_EXPORT_STATE: WorkbenchExportState = {
  status: "unknown",
  missing: [],
  key: null,
};

/** Builds display state only; the loaded PatchBundle remains the audio source of truth. */
export function buildWorkbenchViewModel(
  bundle: PatchBundle<unknown>,
  selectedPadIndex?: number,
  exportState: WorkbenchExportState = DEFAULT_EXPORT_STATE,
): WorkbenchViewModel {
  const metadata = bundle.patch.metadata as Record<string, unknown>;
  const selectedPad = bundle.patch.pads.find((pad) => pad.index === selectedPadIndex);
  const byElementId = new Map(bundle.patch.elements.map((element) => [element.element_id, element]));
  const summarizeElement = (elementId: string): WorkbenchElementSummary => {
    const element = byElementId.get(elementId);
    return {
      elementId,
      name: element?.name ?? elementId,
      kind: element?.kind ?? "unknown",
      sourcePath: element?.source_path ?? null,
      status: bundle.missingElementIds.has(elementId)
        ? "missing"
        : bundle.playableElementIds.has(elementId)
          ? "ready"
          : "unavailable",
    };
  };
  const unmapped = Array.isArray(metadata.unmapped_element_ids)
    ? metadata.unmapped_element_ids.filter((id): id is string => typeof id === "string")
    : [];
  const blockers = [
    ...bundle.warnings,
    ...[...bundle.missingElementIds].map((id) => `missing audio: ${id}`),
    ...exportState.missing.map((item) => `export missing: ${item}`),
  ];

  return {
    patchId: bundle.patch.patch_id,
    schema: bundle.patch.schema,
    bpm: bundle.patch.bpm,
    key: exportState.key,
    durationSeconds: bundle.patch.loop_seconds,
    padCount: 16,
    selectedPad,
    selectedPadSources: selectedPad ? padElementIds(selectedPad).map(summarizeElement) : [],
    elements: bundle.patch.elements.map((element) => summarizeElement(element.element_id)),
    quality: {
      status: typeof metadata.status === "string" ? metadata.status : "unknown",
      score:
        typeof metadata.score === "number" || typeof metadata.score === "string"
          ? metadata.score
          : null,
    },
    unmappedElementIds: unmapped,
    warnings: [...bundle.warnings],
    readiness:
      exportState.status === "partial"
        ? "partial"
        : blockers.length === 0
          ? "ready"
          : "needs-review",
    blockers,
  };
}
