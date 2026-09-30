// The last Project this browser opened. It is a per-device Host convenience,
// never Project Truth: it only chooses which local Project to reopen at boot,
// and a missing, unreadable or stale value simply falls back to the library.
const LAST_PROJECT_KEY = "lmdj.creator.last-project.v1";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export interface LastProjectStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

function defaultStorage(): LastProjectStorage | null {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;
  }
}

export function readLastProjectId(
  storage: LastProjectStorage | null = defaultStorage(),
): string | null {
  try {
    const value = storage?.getItem(LAST_PROJECT_KEY) ?? null;
    return value !== null && UUID_PATTERN.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function writeLastProjectId(
  projectId: string,
  storage: LastProjectStorage | null = defaultStorage(),
): void {
  if (!UUID_PATTERN.test(projectId)) return;
  try {
    storage?.setItem(LAST_PROJECT_KEY, projectId);
  } catch {
    // Storage can be unavailable or full; the next boot opens the library.
  }
}
