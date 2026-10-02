// The last Project this browser opened. It is a per-device Host convenience,
// never Project Truth: it only chooses which local Project to reopen at boot,
// and a missing, unreadable or stale value simply falls back to the library.
//
// It lives in IndexedDB, not localStorage. Chromium commits localStorage
// lazily and rate-limits its commits, so a crash within about a minute of an
// open lost the write, and the next boot reopened an older Project and skipped
// the interrupted recording's recovery (#1726). An IndexedDB write survives the
// process once its transaction completes.
const DATABASE_NAME = "lmdj.creator.host";
const DATABASE_VERSION = 1;
const STORE_NAME = "settings";
const LAST_PROJECT_KEY = "last-project.v1";
const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

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
// the read counts as nothing remembered, the same fallback as a missing value.
const READ_BOUND_MS = 5_000;

export async function readLastProjectId(
  factory: IDBFactory | null = defaultFactory(),
  boundMs = READ_BOUND_MS,
): Promise<string | null> {
  if (factory === null) return null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const bound = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), boundMs);
  });
  try {
    // A read sees every earlier write from this page.
    const read = pendingWrites.then(() => readStoredId(factory));
    return await Promise.race([read, bound]);
  } finally {
    clearTimeout(timer);
  }
}

async function readStoredId(factory: IDBFactory): Promise<string | null> {
  try {
    const database = await openDatabase(factory);
    try {
      const value = await new Promise<unknown>((resolve, reject) => {
        const request = database.transaction(STORE_NAME, "readonly")
          .objectStore(STORE_NAME).get(LAST_PROJECT_KEY);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return typeof value === "string" && UUID_PATTERN.test(value)
        ? value
        : null;
    } finally {
      database.close();
    }
  } catch {
    return null;
  }
}

// Resolves once the write has committed, or when it could not be stored.
// Writes run one after another, so the last call is the one remembered
// whichever of their connections opens first.
export function writeLastProjectId(
  projectId: string,
  factory: IDBFactory | null = defaultFactory(),
): Promise<void> {
  const write = pendingWrites.then(() => storeId(projectId, factory));
  pendingWrites = write;
  return write;
}

async function storeId(
  projectId: string,
  factory: IDBFactory | null,
): Promise<void> {
  if (factory === null || !UUID_PATTERN.test(projectId)) return;
  try {
    const database = await openDatabase(factory);
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put(projectId, LAST_PROJECT_KEY);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
    } finally {
      database.close();
    }
  } catch {
    // Storage can be unavailable or full; the next boot opens the library.
  }
}
