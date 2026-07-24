import type { Patch, PatchBundle } from "../../patch/loader";

export type WorkbenchMode = "source" | "performance" | "export";

export type WorkbenchReadiness = "ready" | "needs-review" | "partial";

export interface WorkbenchExportState {
  status: "unknown" | "complete" | "partial";
  missing: string[];
  key: string | null;
}

export interface WorkbenchViewModel {
  patchId: string;
  bpm: number;
  key: string | null;
  durationSeconds: number;
  padCount: 16;
  selectedPad?: Patch["pads"][number];
  readiness: WorkbenchReadiness;
  blockers: string[];
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
  const blockers = [
    ...bundle.warnings,
    ...[...bundle.missingElementIds].map((id) => `missing audio: ${id}`),
    ...exportState.missing.map((item) => `export missing: ${item}`),
  ];

  return {
    patchId: bundle.patch.patch_id,
    bpm: bundle.patch.bpm,
    key: exportState.key,
    durationSeconds: bundle.patch.loop_seconds,
    padCount: 16,
    selectedPad: bundle.patch.pads.find((pad) => pad.index === selectedPadIndex),
    readiness:
      exportState.status === "partial"
        ? "partial"
        : blockers.length === 0
          ? "ready"
          : "needs-review",
    blockers,
  };
}
