import { loadPatch, type PatchBundle } from "../patch/loader";

const DEFAULT_BASE = "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly detail?: unknown,
  ) {
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
  if (!res.ok) {
    let detail: unknown;
    try {
      const body = (await res.json()) as { detail?: unknown };
      detail = body.detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(uploadErrorMessage(res.status, detail), res.status, detail);
  }
  const body = (await res.json()) as { job_id: string };
  return body.job_id;
}

function uploadErrorMessage(status: number, detail: unknown): string {
  if (typeof detail === "string" && detail) return detail;
  if (!detail || typeof detail !== "object") {
    return `upload failed (HTTP ${status})`;
  }
  const value = detail as Record<string, unknown>;
  if (value.code === "file_too_large" && typeof value.max_bytes === "number") {
    return `文件超过最大限制：${value.max_bytes} bytes`;
  }
  if (value.code === "unsupported_audio" && Array.isArray(value.supported)) {
    return `不支持的音频格式；支持 ${value.supported.join(", ")}`;
  }
  if (
    value.code === "duration_too_long" &&
    typeof value.max_duration_seconds === "number"
  ) {
    return `音频时长超过最大限制：${value.max_duration_seconds} 秒`;
  }
  return `upload failed (HTTP ${status})`;
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
