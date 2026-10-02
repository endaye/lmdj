// The per-device metronome on/off preference. It is a Host monitoring
// preference, never Project Truth (2026-10-02 tempo/metronome decision, item
// 6): it lives in the same IndexedDB Host settings store as the last-Project
// memory, under its own key, and a missing, unreadable or corrupted value
// reads as the default off.
//
// It lives in IndexedDB, not localStorage, for the reason last_project.ts
// records: Chromium commits localStorage lazily and rate-limits its commits,
// so a crash can lose a recent write (#1726). An IndexedDB write survives the
// process once its transaction completes.
const DATABASE_NAME = "lmdj.creator.host";
const DATABASE_VERSION = 1;
const STORE_NAME = "settings";
const METRONOME_KEY = "metronome.v1";

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
// the read counts as the default off, the same fallback as a missing value.
const READ_BOUND_MS = 5_000;

export async function readMetronomePreference(
  factory: IDBFactory | null = defaultFactory(),
  boundMs = READ_BOUND_MS,
): Promise<boolean> {
  if (factory === null) return false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const bound = new Promise<boolean>((resolve) => {
    timer = setTimeout(() => resolve(false), boundMs);
  });
  try {
    // A read sees every earlier write from this page.
    const read = pendingWrites.then(() => readStoredPreference(factory));
    return await Promise.race([read, bound]);
  } finally {
    clearTimeout(timer);
  }
}

async function readStoredPreference(factory: IDBFactory): Promise<boolean> {
  try {
    const database = await openDatabase(factory);
    try {
      const value = await new Promise<unknown>((resolve, reject) => {
        const request = database.transaction(STORE_NAME, "readonly")
          .objectStore(STORE_NAME).get(METRONOME_KEY);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      // Only an exact stored `true` turns the metronome on; anything else —
      // absent, or a value some other writer corrupted — is the default off.
      return value === true;
    } finally {
      database.close();
    }
  } catch {
    return false;
  }
}

// Resolves once the write has committed, or when it could not be stored.
// Writes run one after another, so the last call is the one remembered
// whichever of their connections opens first.
export function writeMetronomePreference(
  on: boolean,
  factory: IDBFactory | null = defaultFactory(),
): Promise<void> {
  const write = pendingWrites.then(() => storePreference(on, factory));
  pendingWrites = write;
  return write;
}

async function storePreference(
  on: boolean,
  factory: IDBFactory | null,
): Promise<void> {
  if (factory === null) return;
  try {
    const database = await openDatabase(factory);
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put(on === true, METRONOME_KEY);
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
