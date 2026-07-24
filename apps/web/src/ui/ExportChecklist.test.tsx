import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  type ApiClient,
  type CreatorExportStatus,
} from "../api/client";
import { ExportChecklist } from "./ExportChecklist";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const completeStatus: CreatorExportStatus = {
  status: "complete",
  downloadable: true,
  items: {
    stems: { status: "review", paths: ["stems/drums.wav"] },
    samples: { status: "ready", paths: ["samples/kick.wav"] },
    midi: { status: "ready", paths: ["midi/chart.mid"] },
    music: { status: "ready", missing: [] },
  },
  missing: [],
  warnings: ["optional stems unavailable: vocals"],
  music: {
    bpm: 90,
    key: { value: "A minor", confidence: 0.72 },
    time_signature: { numerator: 4, denominator: 4, source: "pipeline" },
    loop: { seconds: 10.67, steps: 64, beats: 16, bars: 4 },
  },
};

function api(
  overrides: Partial<ApiClient> = {},
): ApiClient {
  return {
    uploadSong: vi.fn(),
    pollJob: vi.fn(),
    fetchPatchBundle: vi.fn(),
    fetchCreatorExportStatus: vi.fn(),
    downloadCreatorExport: vi
      .fn<ApiClient["downloadCreatorExport"]>()
      .mockResolvedValue(new Blob(["pack"], { type: "application/zip" })),
    ...overrides,
  };
}

function StatefulChecklist({
  initialStatus = completeStatus,
  apiClient,
}: {
  initialStatus?: CreatorExportStatus;
  apiClient: ApiClient;
}) {
  const [status, setStatus] = useState(initialStatus);
  return (
    <ExportChecklist
      apiBase="http://api.test/"
      jobId="job123"
      status={status}
      apiClient={apiClient}
      onStatusChange={setStatus}
    />
  );
}

describe("ExportChecklist", () => {
  it("shows all four server item states with text, icons, and status borders", () => {
    const status: CreatorExportStatus = {
      ...completeStatus,
      status: "partial",
      downloadable: false,
      items: {
        stems: { status: "review", paths: ["stems/drums.wav"] },
        samples: { status: "ready", paths: ["samples/kick.wav"] },
        midi: { status: "missing", paths: [] },
        music: { status: "ready", missing: [] },
      },
      missing: ["midi"],
    };

    render(<StatefulChecklist initialStatus={status} apiClient={api()} />);

    const expected = [
      ["Stems", "Review", "review"],
      ["Samples / Slices", "Ready", "ready"],
      ["MIDI", "Missing", "missing"],
      ["BPM / Key / Time Signature / Loop Metadata", "Ready", "ready"],
    ] as const;
    for (const [label, visibleStatus, dataStatus] of expected) {
      const row = screen.getByTestId(
        `export-item-${label.startsWith("BPM") ? "music" : label.split(" ")[0].toLowerCase()}`,
      );
      expect(row).toHaveAttribute("data-status", dataStatus);
      expect(row).toHaveTextContent(label);
      expect(row).toHaveTextContent(visibleStatus);
      expect(within(row).getByTestId("export-state-icon")).not.toBeEmptyDOMElement();
    }
  });

  it("labels a complete pack with warnings as Review and still downloads it", async () => {
    const download = vi
      .fn<ApiClient["downloadCreatorExport"]>()
      .mockResolvedValue(new Blob(["pack"], { type: "application/zip" }));
    const createObjectURL = vi.fn(() => "blob:creator-pack");
    const revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    render(<StatefulChecklist apiClient={api({ downloadCreatorExport: download })} />);

    expect(screen.getByTestId("export-overall")).toHaveTextContent("Review");
    const button = screen.getByRole("button", { name: /Download Creator Pack/i });
    expect(button).toBeEnabled();
    await userEvent.click(button);

    expect(download).toHaveBeenCalledWith("http://api.test/", "job123");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:creator-pack");
  });

  it("turns a 409 into Partial with the server missing list and never creates a download", async () => {
    const detail = {
      code: "export_incomplete",
      missing: ["music.key", "samples/snare.wav", "chart.mid"],
    };
    const download = vi
      .fn<ApiClient["downloadCreatorExport"]>()
      .mockRejectedValue(new ApiError("incomplete", 409, detail));
    const createObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });

    render(<StatefulChecklist apiClient={api({ downloadCreatorExport: download })} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Download Creator Pack/i }),
    );

    expect(await screen.findByTestId("export-overall")).toHaveTextContent(
      "Partial",
    );
    expect(screen.getByTestId("export-missing")).toHaveTextContent(
      "music.key、samples/snare.wav、chart.mid",
    );
    expect(screen.getByTestId("export-item-music")).toHaveTextContent("Missing");
    expect(screen.getByTestId("export-item-samples")).toHaveTextContent("Missing");
    expect(screen.getByTestId("export-item-midi")).toHaveTextContent("Missing");
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });

  it("keeps a failed download retryable and completes the Blob URL lifecycle on retry", async () => {
    const download = vi
      .fn<ApiClient["downloadCreatorExport"]>()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(new Blob(["pack"], { type: "application/zip" }));
    const createObjectURL = vi.fn(() => "blob:retry-pack");
    const revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    render(<StatefulChecklist apiClient={api({ downloadCreatorExport: download })} />);
    await userEvent.click(
      screen.getByRole("button", { name: /Download Creator Pack/i }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
    await userEvent.click(screen.getByRole("button", { name: /Retry/i }));

    await waitFor(() => expect(download).toHaveBeenCalledTimes(2));
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:retry-pack");
  });
});
