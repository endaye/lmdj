// The per-device SEQ SNAP boundary preference: where a playing-state Pattern
// switch queues (#1958 S4). It is a Host device preference, never Project
// Truth (2026-10-10 pattern-switch decision): it lives in the same IndexedDB
// Host settings store as the last-Project memory, under its own key, and a
// missing, unreadable or corrupted value reads as the default 1 BAR.
//
// It lives in IndexedDB, not localStorage, for the reason last_project.ts
// records: Chromium commits localStorage lazily and rate-limits its commits,
// so a crash can lose a recent write (#1726). An IndexedDB write survives the
// process once its transaction completes.
export type SeqSnap = "beat" | "bar" | "pattern_end";

const DATABASE_NAME = "lmdj.creator.host";
const DATABASE_VERSION = 1;
const STORE_NAME = "settings";
const SEQ_SNAP_KEY = "seq-snap.v1";
const SEQ_SNAP_VALUES: readonly string[] = ["beat", "bar", "pattern_end"];
const DEFAULT_SEQ_SNAP: SeqSnap = "bar";

function isSeqSnap(value: unknown): value is SeqSnap {
  return typeof value === "string" && SEQ_SNAP_VALUES.includes(value);
}

function defaultFactory(): IDBFactory | null {
  try {
    return globalThis.indexedDB ?? null;
  } catch {
    return null;
  }
}

function openDatabase(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => {
      const database = request.result;
      // A later schema version opened elsewhere must not wait on this one.
      database.onversionchange = () => database.close();
      resolve(database);
    };
    request.onerror = () => reject(request.error);
  });
}

let pendingWrites: Promise<void> = Promise.resolve();

// A browser that never settles the open must not hold boot: past this bound
// the read counts as the default 1 BAR, the same fallback as a missing value.
const READ_BOUND_MS = 5_000;

export async function readSeqSnapPreference(
  factory: IDBFactory | null = defaultFactory(),
  boundMs = READ_BOUND_MS,
): Promise<SeqSnap> {
  if (factory === null) return DEFAULT_SEQ_SNAP;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const bound = new Promise<SeqSnap>((resolve) => {
    timer = setTimeout(() => resolve(DEFAULT_SEQ_SNAP), boundMs);
  });
  try {
    // A read sees every earlier write from this page.
    const read = pendingWrites.then(() => readStoredPreference(factory));
    return await Promise.race([read, bound]);
  } finally {
    clearTimeout(timer);
  }
}

async function readStoredPreference(factory: IDBFactory): Promise<SeqSnap> {
  try {
    const database = await openDatabase(factory);
    try {
      const value = await new Promise<unknown>((resolve, reject) => {
        const request = database.transaction(STORE_NAME, "readonly")
          .objectStore(STORE_NAME).get(SEQ_SNAP_KEY);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      // Only an exact stored member is a choice; anything else — absent, or a
      // value some other writer corrupted — is the default 1 BAR.
      return isSeqSnap(value) ? value : DEFAULT_SEQ_SNAP;
    } finally {
      database.close();
    }
  } catch {
    return DEFAULT_SEQ_SNAP;
  }
}

// Resolves once the write has committed, or when it could not be stored.
// Writes run one after another, so the last call is the one remembered
// whichever of their connections opens first.
export function writeSeqSnapPreference(
  snap: SeqSnap,
  factory: IDBFactory | null = defaultFactory(),
): Promise<void> {
  if (!isSeqSnap(snap)) throw new TypeError("Invalid sequence snap");
  const write = pendingWrites.then(() => storePreference(snap, factory));
  pendingWrites = write;
  return write;
}

async function storePreference(
  snap: SeqSnap,
  factory: IDBFactory | null,
): Promise<void> {
  if (factory === null) return;
  try {
    const database = await openDatabase(factory);
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put(snap, SEQ_SNAP_KEY);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
    } finally {
      database.close();
    }
  } catch {
    // Storage can be unavailable or full; the next boot reads the default.
  }
}
