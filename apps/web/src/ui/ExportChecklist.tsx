import { useState } from "react";
import {
  ApiError,
  type ApiClient,
  type CreatorExportStatus,
  type ExportItemStatus,
} from "../api/client";

const ITEMS = [
  ["stems", "Stems"],
  ["samples", "Samples / Slices"],
  ["midi", "MIDI"],
  ["music", "BPM / Key / Time Signature / Loop Metadata"],
] as const;

const STATUS_PRESENTATION: Record<
  ExportItemStatus,
  { icon: string; label: string }
> = {
  ready: { icon: "✓", label: "Ready" },
  review: { icon: "!", label: "Review" },
  missing: { icon: "×", label: "Missing" },
};

type RequestState =
  | { kind: "idle" }
  | { kind: "downloading" }
  | { kind: "error"; message: string };

export function ExportChecklist({
  apiBase,
  jobId,
  patchId,
  status,
  apiClient,
  onStatusChange,
}: {
  apiBase: string;
  jobId: string;
  patchId: string;
  status: CreatorExportStatus;
  apiClient: ApiClient;
  onStatusChange: (status: CreatorExportStatus) => void;
}) {
  const [request, setRequest] = useState<RequestState>({ kind: "idle" });
  const overall = overallStatus(status);

  const download = async () => {
    setRequest({ kind: "downloading" });
    try {
      const blob = await apiClient.downloadCreatorExport(apiBase, jobId);
      const url = URL.createObjectURL(blob);
      try {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = `creator-export-${patchId}.zip`;
        anchor.click();
      } finally {
        URL.revokeObjectURL(url);
      }
      setRequest({ kind: "idle" });
    } catch (error) {
      const missing = missingFromConflict(error);
      if (missing) {
        onStatusChange(applyServerMissing(status, missing));
      }
      setRequest({ kind: "error", message: errorMessage(error) });
    }
  };

  return (
    <section className="export-checklist" data-testid="export-checklist">
      <header className="export-checklist__header">
        <span>Export</span>
        <h2>导出 Creator Pack</h2>
      </header>

      <div
        className="export-overall"
        data-testid="export-overall"
        data-status={overall.toLowerCase()}
      >
        <span aria-hidden="true">
          {overall === "Ready" ? "✓" : overall === "Review" ? "!" : "×"}
        </span>
        <strong>{overall}</strong>
      </div>

      <ul className="export-items">
        {ITEMS.map(([key, label]) => {
          const item = status.items[key];
          const presentation = STATUS_PRESENTATION[item.status];
          return (
            <li
              key={key}
              data-testid={`export-item-${key}`}
              data-status={item.status}
            >
              <span
                className="export-state-icon"
                data-testid="export-state-icon"
                aria-hidden="true"
              >
                {presentation.icon}
              </span>
              <span>{label}</span>
              <strong>{presentation.label}</strong>
            </li>
          );
        })}
      </ul>

      {status.warnings.length > 0 && (
        <div className="export-warnings">
          <strong>Review notes</strong>
          <ul>
            {status.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      {status.missing.length > 0 && (
        <p className="export-missing" data-testid="export-missing">
          <strong>Missing:</strong> {status.missing.join("、")}
        </p>
      )}

      {request.kind === "error" && (
        <p className="export-request-error" role="alert">
          {request.message}
        </p>
      )}

      <button
        type="button"
        className="export-download"
        disabled={
          request.kind === "downloading" ||
          (!status.downloadable && request.kind !== "error")
        }
        onClick={() => void download()}
      >
        {request.kind === "downloading"
          ? "Preparing…"
          : request.kind === "error"
            ? "Retry"
            : "Download Creator Pack"}
      </button>
    </section>
  );
}

function overallStatus(
  status: CreatorExportStatus,
): "Ready" | "Review" | "Partial" {
  if (
    status.status === "partial" ||
    !status.downloadable ||
    status.missing.length > 0
  ) {
    return "Partial";
  }
  if (
    status.warnings.length > 0 ||
    Object.values(status.items).some((item) => item.status === "review")
  ) {
    return "Review";
  }
  return "Ready";
}

function missingFromConflict(error: unknown): string[] | null {
  if (
    !(error instanceof ApiError) ||
    error.status !== 409 ||
    !error.detail ||
    typeof error.detail !== "object"
  ) {
    return null;
  }
  const missing = (error.detail as Record<string, unknown>).missing;
  return Array.isArray(missing) &&
    missing.every((item): item is string => typeof item === "string")
    ? missing
    : null;
}

function applyServerMissing(
  status: CreatorExportStatus,
  missing: string[],
): CreatorExportStatus {
  const misses = (prefixes: string[]) =>
    missing.some((item) =>
      prefixes.some(
        (prefix) => item === prefix || item.startsWith(`${prefix}/`) ||
          item.startsWith(`${prefix}.`),
      ),
    );
  return {
    ...status,
    status: "partial",
    downloadable: false,
    missing,
    items: {
      stems: {
        ...status.items.stems,
        status: misses(["stems"]) ? "missing" : status.items.stems.status,
      },
      samples: {
        ...status.items.samples,
        status: misses(["samples"]) ? "missing" : status.items.samples.status,
      },
      midi: {
        ...status.items.midi,
        status: misses(["midi", "chart.mid"])
          ? "missing"
          : status.items.midi.status,
      },
      music: {
        ...status.items.music,
        status: misses(["music"]) ? "missing" : status.items.music.status,
        missing: missing.filter((item) => item.startsWith("music.")),
      },
    },
  };
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
