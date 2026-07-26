export const STORAGE_KEY = "lmdj.upload-submissions.v1";

export interface StoredSubmission {
  submissionId: string;
  jobId: string | null;
  controlToken?: string | null;
  base: string;
  fileName: string;
  submittedAt: string;
}

function isStoredSubmission(value: unknown): value is StoredSubmission {
  if (!value || typeof value !== "object") return false;
  const record = value as Record<string, unknown>;
  return (
    typeof record.submissionId === "string" &&
    (typeof record.jobId === "string" || record.jobId === null) &&
    (
      record.controlToken === undefined ||
      record.controlToken === null ||
      typeof record.controlToken === "string"
    ) &&
    typeof record.base === "string" &&
    typeof record.fileName === "string" &&
    typeof record.submittedAt === "string"
  );
}

export function loadSubmissions(storage: Storage): StoredSubmission[] {
  const raw = storage.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.every(isStoredSubmission)) return [];
    return parsed;
  } catch {
    return [];
  }
}

export function saveSubmissions(
  storage: Storage,
  submissions: StoredSubmission[],
): void {
  storage.setItem(STORAGE_KEY, JSON.stringify(submissions));
}

export function upsertSubmission(
  storage: Storage,
  submission: StoredSubmission,
): StoredSubmission[] {
  const current = loadSubmissions(storage);
  const index = current.findIndex(
    (candidate) => candidate.submissionId === submission.submissionId,
  );
  const next =
    index === -1
      ? [...current, submission]
      : current.map((candidate, candidateIndex) =>
          candidateIndex === index ? submission : candidate
        );
  saveSubmissions(storage, next);
  return next;
}

export function removeSubmission(
  storage: Storage,
  submissionId: string,
): StoredSubmission[] {
  const next = loadSubmissions(storage).filter(
    (submission) => submission.submissionId !== submissionId,
  );
  saveSubmissions(storage, next);
  return next;
}
