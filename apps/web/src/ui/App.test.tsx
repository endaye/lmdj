import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "../engine/AudioEngine";
import { App } from "./App";
import type { ApiClient, JobStatus } from "../api/client";
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
    expect(screen.getByTestId("pad-matrix")).toBeInTheDocument();
    expect(screen.getByTestId("pattern-surface")).toBeInTheDocument();
    expect(screen.getByText(/BPM/)).toBeInTheDocument();
    expect(screen.getByTestId("status-bar")).toHaveTextContent("Pads 01–16");
    expect(screen.getByTestId("status-bar")).toHaveTextContent(/MIDI Bank.*不适用/i);
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
    uploadSong: async () => "job123",
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

  it("shows truthful input validation until upload returns a job id", async () => {
    let resolveUpload: ((jobId: string) => void) | undefined;
    const uploadSong = vi.fn<ApiClient["uploadSong"]>(
      () =>
        new Promise<string>((resolve) => {
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

    resolveUpload?.("job123");

    await waitFor(() =>
      expect(screen.getByTestId("processing-stage-queued")).toHaveAttribute(
        "aria-current",
        "step",
      ),
    );
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
      .mockResolvedValueOnce("job-new");
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
