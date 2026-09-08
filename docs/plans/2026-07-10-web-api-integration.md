# Web → API Integration Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `apps/web` 加"填 API 地址 → 传歌 → 轮询 job → 玩到 patch"入口，与拖目录/示例并存，播放器零改动。

**Architecture:** 新增 `src/api/client.ts`（纯 fetch，无 React，mock fetch 可测）；`App.tsx` 状态机加 `uploading` 态 + landing 第三入口；三条加载路（拖目录/示例/API）汇成 `Map<path, ArrayBuffer>` 复用同一 `loadPatch`。设计依据：`docs/design/2026-07-10-lmdj-web-api-integration-design.md`。

**Tech Stack:** TypeScript、原生 `fetch` / `FormData`、React（仅 App 层）、Vitest + React Testing Library（mock fetch / 注入 fake client）。

## Global Constraints

- 契约纯度延续：API 路径只拉 `patch.json` + `elements[].source_path` 对应 sample，拼 Map 后调**同一个 `loadPatch`**；不碰 lanes/chart。
- `engine` / `PadGrid` / `Transport` / `StepGrid` / `Inspector` / `loader` / `theme` 的既有行为不改（theme 仅追加 uploading 相关 class，不改现有）。
- 现有 App 测试 + 拖目录/示例两条路必须继续通过（App 新增 prop 走可选注入，默认真实实现，与既有 `fetchExample` 同模式）。
- `client.ts` 无 React import；`pollJob` 的 interval/timeout 可注入（测试用短值），默认 1500ms / 300000ms。
- base URL：`normalizeBase` 去尾斜杠，空 → `http://localhost:8000`。
- 错误：上传请求失败 → landing 红字；job `failed` / 轮询超时 → uploading 态显 error + 返回；patch.json 非法 → 现有 `PatchValidationError` → landing；某 sample 非 200 → 进 `missingElementIds`（loader 既有模型），不阻塞。
- 状态色沿用既有变量（`--green` / `--green-dim` / `--red` / `--gray`）。
- Commit scope：`feat(web): ...`（Conventional Commits）。
- 范围外：engine/pad/step/inspector/loader 改动、ideas/生成、鉴权、分享、多 job 历史、进度百分比、断线重连、env 配置。

---

## File Structure

- Create: `apps/web/src/api/client.ts`（normalizeBase / ApiError / JobStatus / uploadSong / pollJob / fetchPatchBundle / ApiClient / defaultApiClient）
- Create: `apps/web/src/api/client.test.ts`
- Modify: `apps/web/src/ui/App.tsx`（加 uploading 态、landing API 面板、注入 apiClient）
- Create: `apps/web/src/ui/UploadPanel.tsx`（landing 的"从 API 加载"块）
- Create: `apps/web/src/ui/UploadingView.tsx`（阶段进度视图）
- Modify: `apps/web/src/ui/theme.css`（追加 upload/stage class）
- Modify: `apps/web/src/ui/App.test.tsx`（加 API 路径测试；保持既有测试不变）

---

### Task 1: API Client（纯 fetch 层）

**Files:**
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/api/client.test.ts`

**Interfaces:**
- Consumes: `loadPatch`、`PatchBundle` from `../patch/loader`。
- Produces:
  - `class ApiError extends Error { status?: number }`
  - `interface JobStatus { state: string; error: string | null; patch_id: string | null; package_dir: string | null; quality: string | null }`
  - `function normalizeBase(base: string): string`
  - `function uploadSong(base: string, file: File): Promise<string>`
  - `interface PollOpts { intervalMs?: number; timeoutMs?: number; sleep?: (ms: number) => Promise<void> }`
  - `function pollJob(base, jobId, onState?, opts?): Promise<JobStatus>`
  - `type DecodeFn = (b: ArrayBuffer) => Promise<unknown>`
  - `function fetchPatchBundle(base, jobId, decode): Promise<PatchBundle<unknown>>`
  - `interface ApiClient { uploadSong; pollJob; fetchPatchBundle }`、`const defaultApiClient: ApiClient`

- [ ] **Step 1: 写 failing 测试**

Create `apps/web/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import golden from "../patch/__fixtures__/patch.golden.json";
import {
  ApiError,
  fetchPatchBundle,
  normalizeBase,
  pollJob,
  uploadSong,
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/api/client.test.ts
```

Expected: FAIL——`Cannot find module './client'`。

- [ ] **Step 3: 实现 client.ts**

Create `apps/web/src/api/client.ts`:

```ts
import { loadPatch, type PatchBundle } from "../patch/loader";

const DEFAULT_BASE = "http://localhost:8000";

export class ApiError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "ApiError";
  }
}

export interface JobStatus {
  state: string;
  error: string | null;
  patch_id: string | null;
  package_dir: string | null;
  quality: string | null;
}

export type DecodeFn = (b: ArrayBuffer) => Promise<unknown>;

export function normalizeBase(base: string): string {
  const trimmed = base.trim();
  if (!trimmed) return DEFAULT_BASE;
  return trimmed.replace(/\/+$/, "");
}

export async function uploadSong(base: string, file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${normalizeBase(base)}/uploads`, { method: "POST", body: form });
  if (!res.ok) throw new ApiError(`upload failed (HTTP ${res.status})`, res.status);
  const body = (await res.json()) as { job_id: string };
  return body.job_id;
}

export interface PollOpts {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const realSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

export async function pollJob(
  base: string,
  jobId: string,
  onState?: (s: JobStatus) => void,
  opts: PollOpts = {},
): Promise<JobStatus> {
  const intervalMs = opts.intervalMs ?? 1500;
  const timeoutMs = opts.timeoutMs ?? 300_000;
  const sleep = opts.sleep ?? realSleep;
  const root = normalizeBase(base);
  const started = Date.now();

  for (;;) {
    const res = await fetch(`${root}/jobs/${jobId}`);
    if (!res.ok) throw new ApiError(`status poll failed (HTTP ${res.status})`, res.status);
    const status = (await res.json()) as JobStatus;
    onState?.(status);
    if (status.state === "completed") return status;
    if (status.state === "failed") throw new ApiError(status.error || "job failed");
    if (Date.now() - started >= timeoutMs) throw new ApiError("job timed out");
    await sleep(intervalMs);
  }
}

export async function fetchPatchBundle(
  base: string,
  jobId: string,
  decode: DecodeFn,
): Promise<PatchBundle<unknown>> {
  const root = normalizeBase(base);
  const patchRes = await fetch(`${root}/jobs/${jobId}/patch`);
  if (!patchRes.ok) throw new ApiError(`patch fetch failed (HTTP ${patchRes.status})`, patchRes.status);
  const patchBytes = await patchRes.arrayBuffer();

  const files = new Map<string, ArrayBuffer>([["patch.json", patchBytes]]);
  const patch = JSON.parse(new TextDecoder().decode(patchBytes)) as {
    elements?: { source_path: string }[];
  };
  for (const el of patch.elements ?? []) {
    const r = await fetch(`${root}/jobs/${jobId}/files/${el.source_path}`);
    if (r.ok) files.set(el.source_path, await r.arrayBuffer());
    // 非 200：跳过，loader 会把该 element 记为 missing
  }
  return loadPatch(files, decode);
}

export interface ApiClient {
  uploadSong: typeof uploadSong;
  pollJob: typeof pollJob;
  fetchPatchBundle: typeof fetchPatchBundle;
}

export const defaultApiClient: ApiClient = { uploadSong, pollJob, fetchPatchBundle };
```

- [ ] **Step 4: 跑测试确认通过**

```bash
npx vitest run src/api/client.test.ts
```

Expected: `8 passed`。

- [ ] **Step 5: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/api
git commit -m "feat(web): api client for upload, poll, and patch bundle fetch"
```

---

### Task 2: App 接入（uploading 态 + landing 面板 + 进度视图）

**Files:**
- Create: `apps/web/src/ui/UploadPanel.tsx`
- Create: `apps/web/src/ui/UploadingView.tsx`
- Modify: `apps/web/src/ui/App.tsx`
- Modify: `apps/web/src/ui/theme.css`
- Modify: `apps/web/src/ui/App.test.tsx`

**Interfaces:**
- Consumes: `ApiClient`、`defaultApiClient`、`JobStatus` from `../api/client`；`loadPatch`/`PatchBundle` 既有。
- Produces: `App` 新增可选 prop `apiClient?: ApiClient`（默认 `defaultApiClient`）；`UploadPanel`、`UploadingView` 组件。

- [ ] **Step 1: 写 failing App 测试（追加，保留既有测试）**

在 `apps/web/src/ui/App.test.tsx` 追加下列 import 与测试块（不改动既有测试；若 `userEvent`/`waitFor` 未 import 则在顶部补上）：

```tsx
import type { ApiClient, JobStatus } from "../api/client";
import type { PatchBundle } from "../patch/loader";

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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run src/ui/App.test.tsx
```

Expected: FAIL——`App` 不接受 `apiClient` prop / 无 `api-panel` testid。

- [ ] **Step 3: 实现 UploadPanel、UploadingView，改 App**

Create `apps/web/src/ui/UploadPanel.tsx`:

```tsx
import { useState } from "react";

export function UploadPanel({ onUpload }: { onUpload: (base: string, file: File) => void }) {
  const [base, setBase] = useState("http://localhost:8000");
  const [file, setFile] = useState<File | null>(null);

  return (
    <div className="upload-panel" data-testid="api-panel">
      <div className="upload-panel-title">从 API 加载（上传歌曲）</div>
      <input
        className="api-base"
        data-testid="api-base-input"
        value={base}
        onChange={(e) => setBase(e.target.value)}
        spellCheck={false}
      />
      <input
        type="file"
        accept="audio/*"
        data-testid="api-file-input"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <button disabled={!file} onClick={() => file && onUpload(base, file)}>
        传歌
      </button>
    </div>
  );
}
```

Create `apps/web/src/ui/UploadingView.tsx`:

```tsx
const STAGES = ["queued", "separating", "patchifying", "completed"];

export function UploadingView({
  state,
  error,
  onBack,
}: {
  state: string;
  error: string | null;
  onBack: () => void;
}) {
  const currentIndex = STAGES.indexOf(state);
  return (
    <div className="uploading" data-testid="uploading">
      <div className="uploading-title">PROCESSING…</div>
      <ol className="stages">
        {STAGES.map((stage, i) => {
          const cls = error
            ? "stage--pending"
            : i < currentIndex
              ? "stage--done"
              : i === currentIndex
                ? "stage--current"
                : "stage--pending";
          return (
            <li key={stage} className={`stage ${cls}`} data-testid={`stage-${stage}`}>
              {stage}
            </li>
          );
        })}
      </ol>
      {error && (
        <div className="uploading-error" data-testid="uploading-error">
          {error}
        </div>
      )}
      {error && <button onClick={onBack}>返回</button>}
    </div>
  );
}
```

Replace the full contents of `apps/web/src/ui/App.tsx` with:

```tsx
import { useCallback, useEffect, useState } from "react";
import { defaultApiClient, type ApiClient } from "../api/client";
import type { AudioEngine } from "../engine/AudioEngine";
import { loadPatch, PatchValidationError, type PatchBundle } from "../patch/loader";
import { DropZone } from "./DropZone";
import { ErrorPanel } from "./ErrorPanel";
import { Inspector } from "./Inspector";
import { PadGrid, PAD_KEYS } from "./PadGrid";
import { StepGrid } from "./StepGrid";
import { Transport } from "./Transport";
import { UploadPanel } from "./UploadPanel";
import { UploadingView } from "./UploadingView";

/** 内置示例：fetch public/example-patch/（浏览器路径；测试注入替身） */
export async function fetchExampleFiles(): Promise<Map<string, ArrayBuffer>> {
  const res = await fetch("example-patch/patch.json");
  if (!res.ok) {
    throw new PatchValidationError(["示例 patch 不存在——先运行 npm run make-example"]);
  }
  const patchBytes = await res.arrayBuffer();
  const files = new Map<string, ArrayBuffer>([["patch.json", patchBytes]]);
  const patch = JSON.parse(new TextDecoder().decode(patchBytes)) as {
    elements?: { source_path: string }[];
  };
  for (const el of patch.elements ?? []) {
    const r = await fetch(`example-patch/${el.source_path}`);
    if (r.ok) files.set(el.source_path, await r.arrayBuffer());
  }
  return files;
}

type AppState =
  | { phase: "landing"; issues: string[] | null }
  | { phase: "uploading"; state: string; error: string | null }
  | { phase: "loaded"; bundle: PatchBundle<unknown> };

export function App({
  engine,
  decode,
  fetchExample = fetchExampleFiles,
  apiClient = defaultApiClient,
}: {
  engine: AudioEngine;
  decode: (b: ArrayBuffer) => Promise<unknown>;
  fetchExample?: () => Promise<Map<string, ArrayBuffer>>;
  apiClient?: ApiClient;
}) {
  const [state, setState] = useState<AppState>({ phase: "landing", issues: null });

  const fail = useCallback((error: unknown) => {
    const issues = error instanceof PatchValidationError ? error.issues : [String(error)];
    setState({ phase: "landing", issues });
  }, []);

  const enterLoaded = useCallback(
    (bundle: PatchBundle<unknown>) => {
      engine.load(bundle);
      setState({ phase: "loaded", bundle });
    },
    [engine],
  );

  const handleFiles = useCallback(
    async (files: Map<string, ArrayBuffer>) => {
      try {
        enterLoaded(await loadPatch(files, decode));
      } catch (error) {
        fail(error);
      }
    },
    [decode, enterLoaded, fail],
  );

  const handleUpload = useCallback(
    async (base: string, file: File) => {
      setState({ phase: "uploading", state: "queued", error: null });
      try {
        const jobId = await apiClient.uploadSong(base, file);
        await apiClient.pollJob(base, jobId, (s) =>
          setState({ phase: "uploading", state: s.state, error: null }),
        );
        enterLoaded(await apiClient.fetchPatchBundle(base, jobId, decode));
      } catch (error) {
        // uploadSong 失败时 pollJob 尚未回调 → state 仍为 "queued" → 回 landing；
        // pollJob/fetch 阶段失败 → state 已被推进（≥separating）→ 停 uploading 显 error。
        setState((prev) =>
          prev.phase === "uploading" && prev.state !== "queued"
            ? { phase: "uploading", state: prev.state, error: String(error) }
            : { phase: "landing", issues: [String(error)] },
        );
      }
    },
    [apiClient, decode, enterLoaded],
  );

  // 键盘：A S D F / Z X C V → pad 0-7（仅 loaded 后生效）
  useEffect(() => {
    if (state.phase !== "loaded") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const index = PAD_KEYS.indexOf(e.key.toUpperCase());
      if (index >= 0) engine.triggerPad(index);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state.phase, engine]);

  if (state.phase === "uploading") {
    return (
      <div className="app">
        <h1>LMDJ PATCH VIEW</h1>
        <UploadingView
          state={state.state}
          error={state.error}
          onBack={() => setState({ phase: "landing", issues: null })}
        />
      </div>
    );
  }

  if (state.phase === "landing") {
    return (
      <div className="app">
        <h1>LMDJ PATCH VIEW</h1>
        <DropZone
          onFiles={(f) => void handleFiles(f)}
          onExample={() => void fetchExample().then(handleFiles, fail)}
        />
        <UploadPanel onUpload={(base, file) => void handleUpload(base, file)} />
        {state.issues && <ErrorPanel issues={state.issues} />}
      </div>
    );
  }

  const { bundle } = state;
  const status = (bundle.patch.metadata as Record<string, unknown> | undefined)?.status;
  return (
    <div className="app">
      {status === "rejected" && (
        <div className="banner-rejected" data-testid="banner-rejected">
          质量分未过阈（status: rejected）——仍可播放，仅作提示
        </div>
      )}
      <Transport engine={engine} bundle={bundle} />
      <div className="workstation">
        <PadGrid engine={engine} bundle={bundle} />
        <Inspector bundle={bundle} />
        <div className="workstation-bottom">
          <StepGrid engine={engine} bundle={bundle} />
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: 追加 theme.css class**

在 `apps/web/src/ui/theme.css` 末尾追加：

```css
.upload-panel {
  margin-top: 16px;
  border: 1px solid var(--green-dim);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.upload-panel-title { font-size: 12px; opacity: 0.8; }
.api-base {
  font: inherit;
  color: var(--green);
  background: #000;
  border: 1px solid var(--green-dim);
  padding: 4px 6px;
}
.uploading { padding: 32px 16px; }
.uploading-title { margin-bottom: 16px; }
.stages { list-style: none; padding: 0; display: flex; gap: 16px; }
.stage { text-transform: uppercase; font-size: 13px; }
.stage--done { color: var(--green-dim); }
.stage--current { color: var(--green); font-weight: bold; }
.stage--pending { color: var(--gray); }
.uploading-error { color: var(--red); margin: 16px 0; white-space: pre-wrap; }
```

- [ ] **Step 5: 跑测试确认通过（含回归）**

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run
```

Expected: 全部通过（既有全部 + client 8 + App 新增 4）。若既有 App 测试因 UploadPanel 的按钮出现而 `getByRole("button")` 歧义，只修**新增**测试的选择器（用 testid/name 精确化），不改既有断言。

- [ ] **Step 6: 构建确认**

```bash
npm run build
```

Expected: `tsc -b && vite build` 成功。

- [ ] **Step 7: Commit**

```bash
cd /Users/endaye/Projects/lmdj
git add apps/web/src/ui
git commit -m "feat(web): api upload entry with job-progress view"
```

---

## Verification

全计划验证（Task 2 之后）：

```bash
cd /Users/endaye/Projects/lmdj/apps/web
npx vitest run          # 全绿（既有 + client 8 + App 新增 4）
npm run build           # 成功
npm run check-contract  # 不受影响，仍绿
```

真实端到端冒烟（**需 demo venv + apps/api**，手动，浏览器）：

```bash
cd /Users/endaye/Projects/lmdj
scripts/dev.sh smoke                                        # 确保 demo venv
apps/api/.venv/bin/uvicorn lmdj_api.app:app --port 8000 &   # 起后端
cd apps/web && npm run dev                                  # 起前端 :5173
# 浏览器 localhost:5173 → API 面板填 http://localhost:8000
# → 选 references/demos/lmdj-song-pipeline/output/testsong/input.wav → 传歌
# → uploading 阶段推进 → ~30s 后进 workstation，可播放
kill %1
```

## Out Of Scope For This Plan

- engine / PadGrid / Transport / StepGrid / Inspector / loader 的改动。
- ideas / 生成入口、鉴权、分享 / remix、多 job 历史、进度百分比、断线重连、env 配置。
- 真实后端自动化 e2e（手动冒烟即可）。

## Self-Review

- Spec 覆盖：apiClient 四函数 + ApiError/JobStatus（Task 1）；base 默认+可改输入框（UploadPanel）；uploading 态阶段高亮（UploadingView）；三条加载路复用 loadPatch（handleUpload → fetchPatchBundle → loadPatch）；错误五情形（上传失败回 landing / job failed 停 uploading / 超时 / patch 非法走 PatchValidationError / sample 404 走 missing）——逐条可指到任务。
- 类型一致性：`ApiClient` 三方法签名在 client.ts 定义、App 注入使用、fakeApi 实现三处一致；`JobStatus.state` 贯穿 pollJob/UploadingView；`loadPatch(files, decode)` 复用既有签名不变。
- 既有回归：App 新增 prop 全可选默认真实实现；landing 只**追加** UploadPanel，DropZone/ErrorPanel 分支不变；theme 只追加不改；既有 App 测试与拖目录/示例路径不受影响。
- 已知取舍：`fetchPatchBundle` 失败但 job 已 completed → 停 uploading 显 error（而非 landing），可接受；uploading→queued 判据用 state 值区分上传失败 vs 轮询失败（简单够用，不引额外标志位）。
