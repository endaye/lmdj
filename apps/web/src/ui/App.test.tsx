import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "../engine/AudioEngine";
import { App } from "./App";
import {
  ApiError,
  type ApiClient,
  type CreatorExportStatus,
  type JobStatus,
} from "../api/client";
import { STORAGE_KEY, type StoredSubmission } from "../jobs/storage";
import type { PatchBundle } from "../patch/loader";

class MemoryStorage implements Storage {
  private readonly values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

beforeEach(() => vi.stubGlobal("localStorage", new MemoryStorage()));
afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

const enc = (data: unknown) => new TextEncoder().encode(JSON.stringify(data)).buffer as ArrayBuffer;
const fakeDecode = async () => ({ fake: "buffer" });
const creatorExportStatus: CreatorExportStatus = {
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

const queueCapacity = {
  max_concurrency: 1,
  processing: 0,
  waiting: 0,
};

function apiJob(
  jobId: string,
  state: string,
  overrides: Partial<JobStatus> = {},
): JobStatus {
  return {
    job_id: jobId,
    state,
    error: null,
    error_code: null,
    patch_id: null,
    package_dir: null,
    quality: null,
    submission_id: "submission-test",
    original_filename: "song.wav",
    created_at: "2026-07-26T00:00:00Z",
    updated_at: "2026-07-26T00:00:01Z",
    queue_position: null,
    capacity: queueCapacity,
    ...overrides,
  };
}

function exampleFiles(patch: unknown): () => Promise<Map<string, ArrayBuffer>> {
  return async () => {
    const files = new Map<string, ArrayBuffer>([["patch.json", enc(patch)]]);
    for (const el of (patch as unknown as Patch).elements) files.set(el.source_path, new ArrayBuffer(8));
    return files;
  };
}

function renderApp(patch: unknown) {
  const engine = new AudioEngine(new FakeAudioContext());
  return render(
    <App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(patch)} />,
  );
}

describe("App", () => {
  it("starts on the landing screen with a drop zone and example button", () => {
    renderApp(golden);
    expect(screen.getByRole("heading", { name: /feed it a sound/i })).toBeInTheDocument();
    expect(screen.getByTestId("workbench-shell")).toBeInTheDocument();
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /示例/i })).toBeInTheDocument();
  });

  it("loads the example patch into the Instrument-first workbench shell", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("workbench-shell")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Performance" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Source" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("pattern-surface")).toBeInTheDocument();
    expect(screen.getByText(/BPM/)).toBeInTheDocument();
    expect(screen.getByTestId("status-bar")).toHaveTextContent("Pads 01–16");
    expect(screen.getByTestId("status-bar")).toHaveTextContent(/MIDI Bank.*不适用/i);
  });

  it("switches between a truthful loaded Source context and the retained Performance instrument", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    await userEvent.click(screen.getByTestId("pad-1"));
    const retainedPad = screen.getByTestId("pad-1");
    const retainedMidiConnect = screen.getByRole("button", {
      name: "Connect MIDI",
    });
    const patchId = (golden as unknown as Patch).patch_id;
    await userEvent.click(screen.getByRole("button", { name: "Source" }));

    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent(
      "已加载来源",
    );
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent(
      "Example package",
    );
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent(patchId);
    expect(screen.getByTestId("loaded-source-panel")).toHaveTextContent(
      "16 个数据 Pad",
    );
    expect(screen.getByTestId("pad-matrix")).not.toBeVisible();
    expect(screen.getByTestId("pattern-surface")).not.toBeVisible();
    expect(retainedMidiConnect).not.toBeVisible();
    expect(screen.getByRole("button", { name: "更换音频" })).toBeEnabled();

    await userEvent.click(screen.getByRole("button", { name: "Performance" }));
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("pattern-surface")).toBeInTheDocument();
    expect(screen.getByTestId("pad-1")).toBe(retainedPad);
    expect(screen.getByRole("button", { name: "Connect MIDI" })).toBe(
      retainedMidiConnect,
    );
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent(
      "Pad 02 · bass",
    );

    await userEvent.click(screen.getByRole("button", { name: "Source" }));
    await userEvent.click(screen.getByRole("button", { name: "更换音频" }));
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.queryByTestId("loaded-source-panel")).not.toBeInTheDocument();
  });

  it("keeps Pattern above all sixteen contract pads and syncs selection into the Inspector", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    const pattern = screen.getByTestId("pattern-surface");
    const matrix = screen.getByTestId("pad-matrix");
    expect(pattern.compareDocumentPosition(matrix)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);

    const pad = screen.getByRole("button", { name: /Pad 2: bass, idle/i });
    await userEvent.click(pad);
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent("Pad 02 · bass");
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent("trigger_element");
    await waitFor(() => expect(pad).toHaveAccessibleName(/Pad 2: bass, selected/i));
  });

  it("names every Pad with its contract index, label, and non-color state", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    const patch = golden as unknown as Patch;
    for (const pad of patch.pads) {
      expect(screen.getByTestId(`pad-${pad.index}`)).toHaveAccessibleName(
        new RegExp(`Pad ${pad.index + 1}: ${pad.label}, (idle|empty|reserved)`),
      );
    }
  });

  it("maps 1–8 and Q–I directly to all sixteen logical Pads", async () => {
    const engine = new AudioEngine(new FakeAudioContext());
    const triggerPad = vi.spyOn(engine, "triggerPad");
    render(<App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(golden)} />);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    for (const key of ["1", "8", "Q", "I"]) {
      fireEvent.keyDown(window, { key });
    }

    expect(triggerPad).toHaveBeenNthCalledWith(1, 0);
    expect(triggerPad).toHaveBeenNthCalledWith(2, 7);
    expect(triggerPad).toHaveBeenNthCalledWith(3, 8);
    expect(triggerPad).toHaveBeenNthCalledWith(4, 15);
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent(
      "Pad 16 · Empty",
    );
  });

  it("keeps keyboard Pad indexes fixed after switching an eight-pad MIDI Bank", async () => {
    localStorage.setItem(
      "lmdj.midi.mapping.v1",
      JSON.stringify({
        mode: "banked-8",
        notes: [36, 37, 38, 39, 40, 41, 42, 43],
      }),
    );
    const engine = new AudioEngine(new FakeAudioContext());
    const triggerPad = vi.spyOn(engine, "triggerPad");
    render(<App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(golden)} />);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    await userEvent.click(screen.getByTestId("pad-0"));
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent(
      "Pad 01 · kick",
    );
    triggerPad.mockClear();
    await userEvent.click(screen.getByRole("button", { name: /Bank B/i }));
    expect(triggerPad).not.toHaveBeenCalled();
    expect(screen.getByTestId("context-inspector-content")).toHaveTextContent(
      "Pad 01 · kick",
    );
    fireEvent.keyDown(window, { key: "1" });
    fireEvent.keyDown(window, { key: "Q" });

    expect(triggerPad).toHaveBeenNthCalledWith(1, 0);
    expect(triggerPad).toHaveBeenNthCalledWith(2, 8);
    expect(screen.getByTestId("status-bar")).toHaveTextContent("MIDI Bank B");
  });

  it("ignores modified, repeated, and editable keyboard events", async () => {
    const engine = new AudioEngine(new FakeAudioContext());
    const triggerPad = vi.spyOn(engine, "triggerPad");
    render(<App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(golden)} />);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    fireEvent.keyDown(window, { key: "1", repeat: true });
    fireEvent.keyDown(window, { key: "1", metaKey: true });
    fireEvent.keyDown(window, { key: "1", ctrlKey: true });
    fireEvent.keyDown(window, { key: "1", altKey: true });

    const input = document.createElement("input");
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    document.body.append(input, editable);
    fireEvent.keyDown(input, { key: "1" });
    fireEvent.keyDown(editable, { key: "Q" });
    input.remove();
    editable.remove();

    expect(triggerPad).not.toHaveBeenCalled();
  });

  it("returns to the upload screen from the workstation via the eject button", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("back-to-upload"));
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.getByTestId("api-panel")).toBeInTheDocument();
  });

  it("shows the error panel on schema-invalid patch and stays on landing", async () => {
    const broken = structuredClone(golden) as unknown as Patch;
    (broken.pads[0] as { action: string }).action = "nope";
    renderApp(broken);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
    expect(screen.getByTestId("error-panel")).toHaveTextContent(
      "patch.json 未通过 lmdj.patch.v1 校验",
    );
    expect(screen.getByTestId("error-panel").textContent).toContain("/pads/0/action");
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
  });

  it("shows the rejected banner when metadata.status is rejected", async () => {
    const rejected = structuredClone(golden) as unknown as Patch;
    (rejected.metadata as Record<string, unknown>).status = "rejected";
    renderApp(rejected);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("banner-rejected")).toBeInTheDocument());
  });
});

function fakeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    uploadSong: async () => apiJob("job123", "queued"),
    fetchJob: async (_base, jobId) => apiJob(jobId, "completed"),
    resolveSubmission: async () => apiJob("job123", "queued"),
    fetchQueueCapacity: async () => queueCapacity,
    pollJob: async (_b, _j, onState) => {
      onState?.({ state: "separating", error: null, patch_id: null, package_dir: null, quality: null });
      const done: JobStatus = { state: "completed", error: null, patch_id: "job123-abc", package_dir: "job123", quality: "passed" };
      onState?.(done);
      return done;
    },
    fetchPatchBundle: async () => {
      const files = await exampleFiles(golden)();
      const { loadPatch } = await import("../patch/loader");
      return (await loadPatch(files, fakeDecode)) as PatchBundle<unknown>;
    },
    fetchCreatorExportStatus: async () => creatorExportStatus,
    downloadCreatorExport: async () =>
      new Blob(["creator pack"], { type: "application/zip" }),
    ...overrides,
  };
}

function renderAppWithApi(api: ApiClient) {
  const engine = new AudioEngine(new FakeAudioContext());
  return render(<App engine={engine} decode={fakeDecode} fetchExample={exampleFiles(golden)} apiClient={api} />);
}

async function submitViaApi() {
  const file = new File([new Uint8Array([1, 2, 3])], "song.wav", { type: "audio/wav" });
  await userEvent.upload(screen.getByTestId("api-file-input"), file);
  await userEvent.click(screen.getByRole("button", { name: /传歌/i }));
}

describe("App API path", () => {
  it("shows the API panel on landing with default base", () => {
    renderAppWithApi(fakeApi());
    expect(screen.getByTestId("api-panel")).toBeInTheDocument();
    expect(screen.getByTestId("api-base-input")).toHaveValue("http://localhost:8000");
  });

  it("uses VITE_API_BASE for the default base when configured", () => {
    vi.stubEnv("VITE_API_BASE", "/api");

    renderAppWithApi(fakeApi());

    expect(screen.getByTestId("api-base-input")).toHaveValue("/api");
  });

  it("upload → uploading view → loaded workstation", async () => {
    renderAppWithApi(fakeApi());
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
  });

  it("loads Creator status once on API Export mode and synchronizes inspector, Key, and readiness", async () => {
    const fetchCreatorExportStatus = vi
      .fn<ApiClient["fetchCreatorExportStatus"]>()
      .mockResolvedValue(creatorExportStatus);
    const engine = new AudioEngine(new FakeAudioContext());
    const stop = vi.spyOn(engine, "stop");
    render(
      <App
        engine={engine}
        decode={fakeDecode}
        fetchExample={exampleFiles(golden)}
        apiClient={fakeApi({ fetchCreatorExportStatus })}
      />,
    );
    const base = screen.getByTestId("api-base-input");
    await userEvent.clear(base);
    await userEvent.type(base, "http://api.test///");
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("pad-1"));
    stop.mockClear();

    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    await waitFor(() =>
      expect(screen.getByTestId("export-checklist")).toBeInTheDocument(),
    );
    expect(fetchCreatorExportStatus).toHaveBeenCalledTimes(1);
    expect(fetchCreatorExportStatus).toHaveBeenCalledWith(
      "http://api.test",
      "job123",
    );
    expect(screen.getByTestId("context-inspector")).toHaveTextContent(
      "导出 Creator Pack",
    );
    expect(screen.getByTestId("app-bar")).toHaveTextContent("Key A minor");
    expect(screen.getByTestId("status-bar")).toHaveTextContent("needs-review");
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("pad-1")).toHaveAttribute("data-selected", "true");
    expect(stop).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    expect(fetchCreatorExportStatus).toHaveBeenCalledTimes(1);
  });

  it("retries a failed export status request without losing the Pad matrix or selection", async () => {
    const fetchCreatorExportStatus = vi
      .fn<ApiClient["fetchCreatorExportStatus"]>()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValueOnce(creatorExportStatus);
    renderAppWithApi(fakeApi({ fetchCreatorExportStatus }));
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("pad-2"));

    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("offline");
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("pad-2")).toHaveAttribute("data-selected", "true");
    await userEvent.click(
      screen.getByRole("button", { name: /Retry Export Status/i }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("export-checklist")).toBeInTheDocument(),
    );
    expect(fetchCreatorExportStatus).toHaveBeenCalledTimes(2);
  });

  it("resets Export mode before loading a new API Job so its status can be requested", async () => {
    const uploadSong = vi
      .fn<ApiClient["uploadSong"]>()
      .mockResolvedValueOnce(apiJob("job-old", "queued"))
      .mockResolvedValueOnce(apiJob("job-new", "queued"));
    const fetchCreatorExportStatus = vi
      .fn<ApiClient["fetchCreatorExportStatus"]>()
      .mockResolvedValue(creatorExportStatus);
    renderAppWithApi(fakeApi({ uploadSong, fetchCreatorExportStatus }));

    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(fetchCreatorExportStatus).toHaveBeenCalledWith(
        "http://localhost:8000",
        "job-old",
      ),
    );
    await userEvent.click(screen.getByTestId("back-to-upload"));

    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    expect(screen.getByRole("button", { name: "Performance" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(
      screen.queryByText("正在读取服务端 Creator Pack 状态…"),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(fetchCreatorExportStatus).toHaveBeenCalledWith(
        "http://localhost:8000",
        "job-new",
      ),
    );
    expect(fetchCreatorExportStatus).toHaveBeenCalledTimes(2);
  });

  it("ignores a late 409 from an old Job download after a new Job is loaded", async () => {
    const uploadSong = vi
      .fn<ApiClient["uploadSong"]>()
      .mockResolvedValueOnce(apiJob("job-old", "queued"))
      .mockResolvedValueOnce(apiJob("job-new", "queued"));
    const nextStatus = structuredClone(creatorExportStatus);
    nextStatus.warnings = [];
    nextStatus.items.stems.status = "ready";
    nextStatus.music.key = { value: "C major", confidence: 0.91 };
    const fetchCreatorExportStatus = vi
      .fn<ApiClient["fetchCreatorExportStatus"]>()
      .mockImplementation(async (_base, jobId) =>
        jobId === "job-old" ? creatorExportStatus : nextStatus
      );
    let rejectOldDownload: ((reason: unknown) => void) | undefined;
    const downloadCreatorExport = vi
      .fn<ApiClient["downloadCreatorExport"]>()
      .mockImplementation(
        () =>
          new Promise<Blob>((_resolve, reject) => {
            rejectOldDownload = reject;
          }),
      );
    renderAppWithApi(
      fakeApi({
        uploadSong,
        fetchCreatorExportStatus,
        downloadCreatorExport,
      }),
    );

    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(screen.getByTestId("export-checklist")).toBeInTheDocument(),
    );
    await userEvent.click(
      screen.getByRole("button", { name: /Download Creator Pack/i }),
    );
    await userEvent.click(screen.getByTestId("back-to-upload"));

    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Source" }));
    await userEvent.click(screen.getByRole("button", { name: "Export" }));
    await waitFor(() =>
      expect(screen.getByTestId("app-bar")).toHaveTextContent("Key C major"),
    );

    await act(async () => {
      rejectOldDownload?.(
        new ApiError(
          "old export incomplete",
          409,
          { code: "export_incomplete", missing: ["chart.mid"] },
        ),
      );
      await Promise.resolve();
    });

    expect(screen.getByTestId("app-bar")).toHaveTextContent("Key C major");
    expect(screen.getByTestId("status-bar")).not.toHaveTextContent("partial");
    expect(screen.getByTestId("export-item-midi")).toHaveTextContent("Ready");
  });

  it("marks the example as remote-only in Export mode without status requests or a fake download", async () => {
    const fetchCreatorExportStatus = vi.fn<
      ApiClient["fetchCreatorExportStatus"]
    >();
    renderAppWithApi(fakeApi({ fetchCreatorExportStatus }));
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByTestId("context-inspector")).toHaveTextContent(
      "仅远端 Job 可导出",
    );
    expect(screen.getByTestId("context-inspector")).toHaveTextContent("Example");
    expect(
      screen.queryByRole("button", { name: /Download Creator Pack/i }),
    ).not.toBeInTheDocument();
    expect(fetchCreatorExportStatus).not.toHaveBeenCalled();
  });

  it("marks a locally picked package as remote-only without requesting status", async () => {
    const fetchCreatorExportStatus = vi.fn<
      ApiClient["fetchCreatorExportStatus"]
    >();
    const { container } = renderAppWithApi(
      fakeApi({ fetchCreatorExportStatus }),
    );
    const patchFile = new File(
      [JSON.stringify(golden)],
      "patch.json",
      { type: "application/json" },
    );
    Object.defineProperty(patchFile, "webkitRelativePath", {
      value: "local-pack/patch.json",
    });
    Object.defineProperty(patchFile, "arrayBuffer", {
      value: async () => enc(golden),
    });
    const sampleFiles = (golden as unknown as Patch).elements.map((element) => {
      const file = new File([new Uint8Array(8)], element.source_path.split("/").at(-1) ?? "sample.wav");
      Object.defineProperty(file, "webkitRelativePath", {
        value: `local-pack/${element.source_path}`,
      });
      Object.defineProperty(file, "arrayBuffer", {
        value: async () => new ArrayBuffer(8),
      });
      return file;
    });
    const input = container.querySelector(
      '.drop-zone input[type="file"]',
    ) as HTMLInputElement;

    await userEvent.upload(input, [patchFile, ...sampleFiles]);
    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: "Export" }));

    expect(screen.getByTestId("context-inspector")).toHaveTextContent(
      "仅远端 Job 可导出",
    );
    expect(screen.getByTestId("context-inspector")).toHaveTextContent("Local");
    expect(fetchCreatorExportStatus).not.toHaveBeenCalled();
  });

  it("shows truthful input validation until upload returns a job id", async () => {
    let resolveUpload: ((status: JobStatus) => void) | undefined;
    const uploadSong = vi.fn<ApiClient["uploadSong"]>(
      () =>
        new Promise<JobStatus>((resolve) => {
          resolveUpload = resolve;
        }),
    );
    renderAppWithApi(fakeApi({
      uploadSong,
      pollJob: async () => await new Promise<JobStatus>(() => {}),
    }));

    await submitViaApi();

    expect(screen.getByTestId("processing-preflight")).toHaveTextContent(
      "Validating Input",
    );
    expect(screen.getByTestId("processing-preflight")).toHaveTextContent(
      "preflight",
    );
    expect(screen.queryByText("Input Validated")).not.toBeInTheDocument();

    resolveUpload?.(apiJob("job123", "queued"));

    await waitFor(() =>
      expect(screen.getByTestId("processing-stage-queued")).toHaveAttribute(
        "aria-current",
        "step",
      ),
    );
  });

  it("keeps two submissions visible while FIFO moves B behind A", async () => {
    const callbacks = new Map<string, (status: JobStatus) => void>();
    const resolvers = new Map<string, (status: JobStatus) => void>();
    const uploadSong = vi
      .fn<ApiClient["uploadSong"]>()
      .mockResolvedValueOnce(
        apiJob("job-a", "queued", {
          original_filename: "song-a.wav",
          capacity: { max_concurrency: 1, processing: 1, waiting: 0 },
        }),
      )
      .mockResolvedValueOnce(
        apiJob("job-b", "queued", {
          original_filename: "song-b.wav",
          queue_position: 1,
          capacity: { max_concurrency: 1, processing: 1, waiting: 1 },
        }),
      );
    const pollJob = vi.fn<ApiClient["pollJob"]>(
      async (_base, jobId, onState) => {
        callbacks.set(jobId, onState ?? (() => undefined));
        if (jobId === "job-a") {
          onState?.(
            apiJob("job-a", "separating", {
              original_filename: "song-a.wav",
              capacity: { max_concurrency: 1, processing: 1, waiting: 0 },
            }),
          );
        } else {
          onState?.(
            apiJob("job-b", "queued", {
              original_filename: "song-b.wav",
              queue_position: 1,
              capacity: { max_concurrency: 1, processing: 1, waiting: 1 },
            }),
          );
        }
        return await new Promise<JobStatus>((resolve) => {
          resolvers.set(jobId, resolve);
        });
      },
    );
    renderAppWithApi(fakeApi({ uploadSong, pollJob }));

    const songA = new File([new Uint8Array([1])], "song-a.wav", {
      type: "audio/wav",
    });
    await userEvent.upload(screen.getByTestId("api-file-input"), songA);
    await userEvent.click(screen.getByRole("button", { name: /传歌/i }));
    await waitFor(() =>
      expect(screen.getByTestId("job-card-job-a")).toHaveTextContent(
        "正在处理",
      ),
    );

    const songB = new File([new Uint8Array([2])], "song-b.wav", {
      type: "audio/wav",
    });
    await userEvent.upload(screen.getByTestId("api-file-input"), songB);
    await userEvent.click(screen.getByRole("button", { name: /传歌/i }));

    await waitFor(() => {
      expect(screen.getByTestId("job-card-job-a")).toHaveTextContent(
        "song-a.wav",
      );
      expect(screen.getByTestId("job-card-job-a")).toHaveTextContent("job-a");
      expect(screen.getByTestId("job-card-job-b")).toHaveTextContent(
        "song-b.wav",
      );
      expect(screen.getByTestId("job-card-job-b")).toHaveTextContent(
        "队列位置 1",
      );
      expect(screen.getByTestId("queue-capacity")).toHaveTextContent(
        "最大并发 1",
      );
      expect(screen.getByTestId("queue-capacity")).toHaveTextContent(
        "正在处理 1",
      );
      expect(screen.getByTestId("queue-capacity")).toHaveTextContent("等待 1");
    });

    await act(async () => {
      const doneA = apiJob("job-a", "completed", {
        patch_id: "patch-a",
        package_dir: "package-a",
        capacity: { max_concurrency: 1, processing: 1, waiting: 0 },
      });
      callbacks.get("job-a")?.(doneA);
      resolvers.get("job-a")?.(doneA);
      await Promise.resolve();
      callbacks.get("job-b")?.(
        apiJob("job-b", "separating", {
          original_filename: "song-b.wav",
          capacity: { max_concurrency: 1, processing: 1, waiting: 0 },
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("job-card-job-a")).toHaveTextContent(
        "处理完成",
      );
      expect(screen.getByTestId("job-card-job-b")).toHaveTextContent(
        "正在处理",
      );
    });
    expect(screen.queryByTestId("pad-matrix")).not.toBeInTheDocument();
  });

  it("restores a stored Job after remount and resumes polling", async () => {
    const stored: StoredSubmission = {
      submissionId: "submission-restored",
      jobId: "job-restored",
      base: "http://localhost:8000",
      fileName: "restored.wav",
      submittedAt: "2026-07-26T01:02:03.000Z",
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify([stored]));
    const fetchJob = vi
      .fn<ApiClient["fetchJob"]>()
      .mockResolvedValue(
        apiJob("job-restored", "separating", {
          submission_id: stored.submissionId,
          original_filename: stored.fileName,
          capacity: { max_concurrency: 1, processing: 1, waiting: 0 },
        }),
      );
    const pollJob = vi.fn<ApiClient["pollJob"]>(
      async () => await new Promise<JobStatus>(() => {}),
    );

    renderAppWithApi(fakeApi({ fetchJob, pollJob }));

    await waitFor(() => {
      expect(fetchJob).toHaveBeenCalledWith(stored.base, stored.jobId);
      expect(pollJob).toHaveBeenCalledWith(
        stored.base,
        stored.jobId,
        expect.any(Function),
      );
      expect(screen.getByTestId("job-card-job-restored")).toHaveTextContent(
        "restored.wav",
      );
      expect(screen.getByTestId("job-card-job-restored")).toHaveTextContent(
        "2026-07-26T00:00:00Z",
      );
    });
  });

  it("resolves a persisted submission after the upload response was lost", async () => {
    const stored: StoredSubmission = {
      submissionId: "submission-lost-response",
      jobId: null,
      base: "http://localhost:8000",
      fileName: "lost.wav",
      submittedAt: "2026-07-26T02:03:04.000Z",
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify([stored]));
    const resolveSubmission = vi
      .fn<ApiClient["resolveSubmission"]>()
      .mockResolvedValue(
        apiJob("job-recovered", "queued", {
          submission_id: stored.submissionId,
          original_filename: stored.fileName,
          queue_position: 1,
        }),
      );
    const pollJob = vi.fn<ApiClient["pollJob"]>(
      async () => await new Promise<JobStatus>(() => {}),
    );

    renderAppWithApi(fakeApi({ resolveSubmission, pollJob }));

    await waitFor(() => {
      expect(resolveSubmission).toHaveBeenCalledWith(
        stored.base,
        stored.submissionId,
      );
      expect(screen.getByTestId("job-card-job-recovered")).toHaveTextContent(
        "job-recovered",
      );
    });
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]")).toEqual([
      expect.objectContaining({ jobId: "job-recovered" }),
    ]);
  });

  it("restores interrupted as a terminal server outcome", async () => {
    const stored: StoredSubmission = {
      submissionId: "submission-interrupted",
      jobId: "job-interrupted",
      base: "http://localhost:8000",
      fileName: "interrupted.wav",
      submittedAt: "2026-07-26T03:04:05.000Z",
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify([stored]));
    const pollJob = vi.fn<ApiClient["pollJob"]>();

    renderAppWithApi(
      fakeApi({
        fetchJob: async () =>
          apiJob("job-interrupted", "interrupted", {
            error: "API service restarted before this Job completed.",
            error_code: "service_interrupted",
            submission_id: stored.submissionId,
            original_filename: stored.fileName,
          }),
        pollJob,
      }),
    );

    await waitFor(() =>
      expect(screen.getByTestId("job-card-job-interrupted")).toHaveTextContent(
        "服务中断",
      ),
    );
    expect(screen.getByTestId("job-card-job-interrupted")).toHaveTextContent(
      "API service restarted before this Job completed.",
    );
    expect(screen.getByTestId("job-card-job-interrupted")).not.toHaveTextContent(
      "Failed to fetch",
    );
    expect(pollJob).not.toHaveBeenCalled();
  });

  it("deduplicates a double click while one submission request is in flight", async () => {
    const uploadSong = vi.fn<ApiClient["uploadSong"]>(
      async () => await new Promise<JobStatus>(() => {}),
    );
    renderAppWithApi(fakeApi({ uploadSong }));
    const file = new File([new Uint8Array([1, 2, 3])], "double.wav", {
      type: "audio/wav",
    });
    await userEvent.upload(screen.getByTestId("api-file-input"), file);
    const submit = screen.getByRole("button", { name: /传歌/i });

    fireEvent.click(submit);
    fireEvent.click(submit);

    await waitFor(() => expect(uploadSong).toHaveBeenCalledTimes(1));
    const submissions = JSON.parse(
      localStorage.getItem(STORAGE_KEY) ?? "[]",
    ) as StoredSubmission[];
    expect(submissions).toHaveLength(1);
    expect(uploadSong.mock.calls[0][2]).toBe(submissions[0].submissionId);
  });

  it("failed job shows error in uploading view with a back button", async () => {
    const { ApiError } = await import("../api/client");
    renderAppWithApi(fakeApi({
      pollJob: async (_b, _j, onState) => {
        onState?.({ state: "separating", error: null, patch_id: null, package_dir: null, quality: null });
        throw new ApiError("demucs boom");
      },
    }));
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("failed-state")).toHaveTextContent("demucs boom"));
    expect(screen.getByTestId("failed-state")).toHaveTextContent("song.wav");
    expect(screen.getByTestId("failed-state")).toHaveTextContent("separating");
    await userEvent.click(screen.getByRole("button", { name: /Back/i }));
    expect(screen.getByTestId("api-panel")).toBeInTheDocument();
  });

  it("preserves the last nonterminal stage when poll reports failed then throws", async () => {
    const { ApiError } = await import("../api/client");
    renderAppWithApi(fakeApi({
      pollJob: async (_base, _jobId, onState) => {
        onState?.({
          state: "separating",
          error: null,
          patch_id: null,
          package_dir: null,
          quality: null,
        });
        onState?.({
          state: "patchifying",
          error: null,
          patch_id: null,
          package_dir: null,
          quality: null,
        });
        onState?.({
          state: "failed",
          error: "mapping failed",
          patch_id: null,
          package_dir: null,
          quality: null,
        });
        throw new ApiError("mapping failed");
      },
    }));

    await submitViaApi();

    await waitFor(() => expect(screen.getByTestId("failed-state")).toBeInTheDocument());
    expect(screen.getByTestId("failed-state")).toHaveTextContent("patchifying");
    expect(screen.getByTestId("failed-state")).not.toHaveTextContent(
      /Failed atfailed/i,
    );
  });

  it.each([
    [
      413,
      { code: "file_too_large", max_bytes: 209715200 },
      "209715200",
    ],
    [
      415,
      { code: "unsupported_audio", supported: ["wav", "mp3"] },
      "wav, mp3",
    ],
    [
      422,
      { code: "duration_too_long", max_duration_seconds: 600 },
      "600",
    ],
    [
      422,
      { code: "audio_probe_timeout", timeout_seconds: 0.25 },
      "音频检查超时：0.25 秒",
    ],
  ])(
    "shows structured preflight detail for HTTP %i",
    async (status, detail, expected) => {
      const { ApiError } = await import("../api/client");
      renderAppWithApi(fakeApi({
        uploadSong: async () => {
          throw new ApiError(`rejected ${expected}`, status, detail);
        },
      }));

      await submitViaApi();

      await waitFor(() =>
        expect(screen.getByTestId("error-panel")).toHaveTextContent(expected),
      );
      expect(screen.getByTestId("error-panel")).toHaveTextContent(
        "上传未通过检查",
      );
      expect(screen.getByTestId("error-panel")).not.toHaveTextContent(
        /upload failed|处理未完成/i,
      );
      expect(screen.getByTestId("failed-state")).toHaveTextContent("song.wav");
      expect(screen.getByTestId("failed-state")).toHaveTextContent("preflight");
    },
  );

  it("keeps an unknown job state visible while processing", async () => {
    renderAppWithApi(fakeApi({
      pollJob: async (_base, _jobId, onState) => {
        onState?.({
          state: "spectralizing",
          error: null,
          patch_id: null,
          package_dir: null,
          quality: null,
        });
        return await new Promise<JobStatus>(() => {});
      },
    }));

    await submitViaApi();

    await waitFor(() => expect(screen.getByText("Unknown")).toBeInTheDocument());
    expect(screen.getAllByText("spectralizing").length).toBeGreaterThan(0);
    expect(screen.getByTestId("workbench-shell")).toBeInTheDocument();
  });

  it("retries a failed upload through preflight and creates a new job", async () => {
    const { ApiError } = await import("../api/client");
    const uploadSong = vi
      .fn<ApiClient["uploadSong"]>()
      .mockRejectedValueOnce(
        new ApiError(
          "too large: 209715200",
          413,
          { code: "file_too_large", max_bytes: 209715200 },
        ),
      )
      .mockResolvedValueOnce(apiJob("job-new", "queued"));
    renderAppWithApi(fakeApi({ uploadSong }));
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("failed-state")).toBeInTheDocument());

    await userEvent.click(screen.getByRole("button", { name: /Retry/i }));

    await waitFor(() => expect(screen.getByTestId("pad-matrix")).toBeInTheDocument());
    expect(uploadSong).toHaveBeenCalledTimes(2);
    expect(uploadSong.mock.calls[1][1].name).toBe("song.wav");
  });

  it("keeps the paper and ink workbench shell for source, processing, and failed", async () => {
    const { ApiError } = await import("../api/client");
    let rejectProcessing: ((reason: unknown) => void) | undefined;
    renderAppWithApi(fakeApi({
      pollJob: async (_base, _jobId, onState) => {
        onState?.({
          state: "separating",
          error: null,
          patch_id: null,
          package_dir: null,
          quality: null,
        });
        return await new Promise<JobStatus>((_resolve, reject) => {
          rejectProcessing = reject;
        });
      },
    }));
    expect(screen.getByTestId("workbench-shell")).toHaveClass("workbench-shell");
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("processing-panel")).toBeInTheDocument());
    expect(screen.getByTestId("app-bar")).toBeInTheDocument();

    rejectProcessing?.(new ApiError("worker stopped"));

    await waitFor(() => expect(screen.getByTestId("failed-state")).toBeInTheDocument());
    expect(screen.getByTestId("app-bar")).toBeInTheDocument();
  });
});
