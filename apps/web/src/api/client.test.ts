import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import {
  ApiError,
  downloadCreatorExport,
  fetchCreatorExportStatus,
  fetchPatchBundle,
  normalizeBase,
  pollJob,
  uploadSong,
  type CreatorExportStatus,
  type JobStatus,
} from "./client";

const fakeDecode = async () => ({ fake: "buffer" });
const noSleep = async () => {};

afterEach(() => {
  vi.restoreAllMocks();
});

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return {
    ok,
    status,
    json: async () => body,
    arrayBuffer: async () => new TextEncoder().encode(JSON.stringify(body)).buffer,
  } as unknown as Response;
}

describe("normalizeBase", () => {
  it("strips trailing slash and defaults when empty", () => {
    expect(normalizeBase("http://x:8000/")).toBe("http://x:8000");
    expect(normalizeBase("  ")).toBe("http://localhost:8000");
    expect(normalizeBase("http://x:8000")).toBe("http://x:8000");
  });
});

describe("uploadSong", () => {
  it("POSTs multipart and returns job_id", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ job_id: "job123", state: "queued" }),
    );
    const file = new File([new Uint8Array([1, 2, 3])], "song.wav", { type: "audio/wav" });

    const jobId = await uploadSong("http://x:8000/", file);

    expect(jobId).toBe("job123");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://x:8000/uploads");
    expect((init as RequestInit).method).toBe("POST");
    expect((init as RequestInit).body).toBeInstanceOf(FormData);
  });

  it("throws ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({}, false, 500));
    await expect(uploadSong("http://x:8000", new File([], "s.wav"))).rejects.toBeInstanceOf(ApiError);
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
  ])("preserves structured HTTP %i upload detail", async (status, detail, visibleValue) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail }, false, status),
    );

    const error = await uploadSong(
      "http://x:8000",
      new File([], "song.wav"),
    ).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(status);
    expect(error.detail).toEqual(detail);
    expect(error.message).toContain(visibleValue);
  });
});

describe("pollJob", () => {
  it("polls until completed, calling onState each round", async () => {
    const seq: JobStatus[] = [
      { state: "queued", error: null, patch_id: null, package_dir: null, quality: null },
      { state: "separating", error: null, patch_id: null, package_dir: null, quality: null },
      { state: "completed", error: null, patch_id: "job123-abc", package_dir: "job123", quality: "passed" },
    ];
    let i = 0;
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(seq[i++]));
    const seen: string[] = [];

    const final = await pollJob("http://x:8000", "job123", (s) => seen.push(s.state), {
      intervalMs: 0,
      timeoutMs: 1000,
      sleep: noSleep,
    });

    expect(final.state).toBe("completed");
    expect(final.patch_id).toBe("job123-abc");
    expect(seen).toEqual(["queued", "separating", "completed"]);
  });

  it("throws ApiError carrying the job error on failed", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ state: "failed", error: "demucs boom", patch_id: null, package_dir: null, quality: null }),
    );
    const err = await pollJob("http://x:8000", "j", undefined, { intervalMs: 0, sleep: noSleep }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(String(err)).toContain("demucs boom");
  });

  it("throws ApiError on timeout", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ state: "separating", error: null, patch_id: null, package_dir: null, quality: null }),
    );
    await expect(
      pollJob("http://x:8000", "j", undefined, { intervalMs: 0, timeoutMs: 0, sleep: noSleep }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});

describe("fetchPatchBundle", () => {
  it("fetches patch.json + samples and builds a bundle via loadPatch", async () => {
    const patch = golden as { elements: { source_path: string }[] };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("/patch")) return jsonResponse(patch);
      return { ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(8) } as unknown as Response;
    });

    const bundle = await fetchPatchBundle("http://x:8000", "job123", fakeDecode);

    expect(bundle.patch.schema).toBe("lmdj.patch.v1");
    expect(bundle.missingElementIds.size).toBe(0);
    expect(bundle.playableElementIds.size).toBe(patch.elements.length);
  });

  it("marks a sample that 404s as missing, without blocking", async () => {
    const patch = golden as { elements: { source_path: string }[] };
    const firstPath = patch.elements[0].source_path;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      if (u.endsWith("/patch")) return jsonResponse(patch);
      if (u.endsWith(firstPath)) return { ok: false, status: 404 } as unknown as Response;
      return { ok: true, status: 200, arrayBuffer: async () => new ArrayBuffer(8) } as unknown as Response;
    });

    const bundle = await fetchPatchBundle("http://x:8000", "job123", fakeDecode);
    const firstId = bundle.patch.elements[0].element_id;
    expect(bundle.missingElementIds.has(firstId)).toBe(true);
  });
});

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

describe("Creator export", () => {
  it("fetches the server inspection as the status source of truth", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(creatorExportStatus));

    await expect(
      fetchCreatorExportStatus("http://x:8000/", "job123"),
    ).resolves.toEqual(creatorExportStatus);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://x:8000/jobs/job123/export/status",
    );
  });

  it("returns the successful Creator export response as a Blob", async () => {
    const blob = new Blob(["creator pack"], { type: "application/zip" });
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => blob,
    } as Response);

    await expect(
      downloadCreatorExport("http://x:8000/", "job123"),
    ).resolves.toBe(blob);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://x:8000/jobs/job123/export",
    );
  });

  it("preserves a 409 missing list in ApiError.detail", async () => {
    const detail = {
      code: "export_incomplete",
      missing: ["music.key", "samples/snare.wav"],
    };
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail }, false, 409),
    );

    const error = await downloadCreatorExport(
      "http://x:8000",
      "job123",
    ).catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.detail).toEqual(detail);
  });

  it("surfaces a network failure without manufacturing a response", async () => {
    const networkError = new TypeError("offline");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(networkError);

    await expect(
      fetchCreatorExportStatus("http://x:8000", "job123"),
    ).rejects.toBe(networkError);
  });
});
