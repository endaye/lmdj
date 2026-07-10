import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import type { Patch } from "../patch/loader";
import { FakeAudioContext } from "../test/fakes";
import { AudioEngine } from "../engine/AudioEngine";
import { App } from "./App";
import type { ApiClient, JobStatus } from "../api/client";
import type { PatchBundle } from "../patch/loader";

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
    expect(screen.getByTestId("drop-zone")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /示例/i })).toBeInTheDocument();
  });

  it("loads the example patch into the workstation view", async () => {
    renderApp(golden);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("pad-grid")).toBeInTheDocument());
    expect(screen.getByText(/BPM/)).toBeInTheDocument();
  });

  it("shows the error panel on schema-invalid patch and stays on landing", async () => {
    const broken = structuredClone(golden) as unknown as Patch;
    (broken.pads[0] as { action: string }).action = "nope";
    renderApp(broken);
    await userEvent.click(screen.getByRole("button", { name: /示例/i }));
    await waitFor(() => expect(screen.getByTestId("error-panel")).toBeInTheDocument());
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

  it("upload → uploading view → loaded workstation", async () => {
    renderAppWithApi(fakeApi());
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("pad-grid")).toBeInTheDocument());
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
    await waitFor(() => expect(screen.getByTestId("uploading-error")).toHaveTextContent("demucs boom"));
    await userEvent.click(screen.getByRole("button", { name: /返回/i }));
    expect(screen.getByTestId("api-panel")).toBeInTheDocument();
  });

  it("upload request failure returns to landing with an error", async () => {
    const { ApiError } = await import("../api/client");
    renderAppWithApi(fakeApi({
      uploadSong: async () => { throw new ApiError("network down"); },
    }));
    await submitViaApi();
    await waitFor(() => expect(screen.getByTestId("error-panel")).toHaveTextContent("network down"));
  });
});
