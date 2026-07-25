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

export interface QueueCapacity {
  max_concurrency: number;
  processing: number;
  waiting: number;
}

export interface JobStatus {
  job_id?: string;
  state: string;
  error: string | null;
  error_code?: string | null;
  patch_id: string | null;
  package_dir: string | null;
  quality: string | null;
  submission_id?: string | null;
  original_filename?: string | null;
  pipeline?: string | null;
  created_at?: string;
  updated_at?: string;
  queue_position?: number | null;
  capacity?: QueueCapacity;
}

export type ExportItemStatus = "ready" | "review" | "missing";

export interface CreatorExportItem {
  status: ExportItemStatus;
  paths?: string[];
  missing?: string[];
}

export interface CreatorExportStatus {
  status: "complete" | "partial";
  downloadable: boolean;
  items: {
    stems: CreatorExportItem;
    samples: CreatorExportItem;
    midi: CreatorExportItem;
    music: CreatorExportItem;
  };
  missing: string[];
  warnings: string[];
  music: {
    bpm?: number;
    key?: { value: string; confidence: number } | null;
    time_signature?: {
      numerator: number;
      denominator: number;
      source: string;
    };
    loop?: {
      seconds: number;
      steps: number;
      beats: number;
      bars: number;
    };
  };
}

export type DecodeFn = (b: ArrayBuffer) => Promise<unknown>;

export function normalizeBase(base: string): string {
  const trimmed = base.trim();
  if (!trimmed) return DEFAULT_BASE;
  return trimmed.replace(/\/+$/, "");
}

export async function uploadSong(
  base: string,
  file: File,
  submissionId: string,
): Promise<JobStatus> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${normalizeBase(base)}/uploads`, {
    method: "POST",
    body: form,
    headers: { "Idempotency-Key": submissionId },
  });
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
  return (await res.json()) as JobStatus;
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
  if (
    value.code === "audio_probe_timeout" &&
    typeof value.timeout_seconds === "number"
  ) {
    return `音频检查超时：${value.timeout_seconds} 秒`;
  }
  return `upload failed (HTTP ${status})`;
}

export interface PollOpts {
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (ms: number) => Promise<void>;
}

const realSleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

async function fetchStatus(url: string): Promise<JobStatus> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new ApiError(
      `status fetch failed (HTTP ${response.status})`,
      response.status,
      await responseDetail(response),
    );
  }
  return (await response.json()) as JobStatus;
}

export async function fetchJob(
  base: string,
  jobId: string,
): Promise<JobStatus> {
  return fetchStatus(`${normalizeBase(base)}/jobs/${jobId}`);
}

export async function resolveSubmission(
  base: string,
  submissionId: string,
): Promise<JobStatus> {
  return fetchStatus(
    `${normalizeBase(base)}/submissions/${encodeURIComponent(submissionId)}`,
  );
}

export async function fetchQueueCapacity(
  base: string,
): Promise<QueueCapacity> {
  const response = await fetch(`${normalizeBase(base)}/queue`);
  if (!response.ok) {
    throw new ApiError(
      `queue fetch failed (HTTP ${response.status})`,
      response.status,
      await responseDetail(response),
    );
  }
  return (await response.json()) as QueueCapacity;
}

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
    const status = await fetchStatus(`${root}/jobs/${jobId}`);
    onState?.(status);
    if (status.state === "completed") return status;
    if (["failed", "cancelled", "interrupted"].includes(status.state)) {
      throw new ApiError(
        status.error || `job ${status.state}`,
        undefined,
        status,
      );
    }
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

async function responseDetail(response: Response): Promise<unknown> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    return body.detail;
  } catch {
    return undefined;
  }
}

export async function fetchCreatorExportStatus(
  base: string,
  jobId: string,
): Promise<CreatorExportStatus> {
  const response = await fetch(
    `${normalizeBase(base)}/jobs/${jobId}/export/status`,
  );
  if (!response.ok) {
    const detail = await responseDetail(response);
    throw new ApiError(
      `export status failed (HTTP ${response.status})`,
      response.status,
      detail,
    );
  }
  return (await response.json()) as CreatorExportStatus;
}

export async function downloadCreatorExport(
  base: string,
  jobId: string,
): Promise<Blob> {
  const response = await fetch(
    `${normalizeBase(base)}/jobs/${jobId}/export`,
  );
  if (!response.ok) {
    const detail = await responseDetail(response);
    throw new ApiError(
      `Creator export failed (HTTP ${response.status})`,
      response.status,
      detail,
    );
  }
  return response.blob();
}

export interface ApiClient {
  uploadSong: typeof uploadSong;
  fetchJob: typeof fetchJob;
  resolveSubmission: typeof resolveSubmission;
  fetchQueueCapacity: typeof fetchQueueCapacity;
  pollJob: typeof pollJob;
  fetchPatchBundle: typeof fetchPatchBundle;
  fetchCreatorExportStatus: typeof fetchCreatorExportStatus;
  downloadCreatorExport: typeof downloadCreatorExport;
}

export const defaultApiClient: ApiClient = {
  uploadSong,
  fetchJob,
  resolveSubmission,
  fetchQueueCapacity,
  pollJob,
  fetchPatchBundle,
  fetchCreatorExportStatus,
  downloadCreatorExport,
};
