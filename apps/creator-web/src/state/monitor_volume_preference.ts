// Device-local listening volume in the existing IndexedDB Host settings.
// A completed transaction survives page/process close; no Project state is written.
const DATABASE_NAME = "lmdj.creator.host";
const DATABASE_VERSION = 1;
const STORE_NAME = "settings";
const MONITOR_VOLUME_KEY = "monitor-volume.v1";

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
// the read counts as the default 100 percent, the same fallback as a missing value.
const READ_BOUND_MS = 5_000;

export async function readMonitorVolumePreference(
  factory: IDBFactory | null = defaultFactory(),
  boundMs = READ_BOUND_MS,
): Promise<number> {
  if (factory === null) return 100;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const bound = new Promise<number>((resolve) => {
    timer = setTimeout(() => resolve(100), boundMs);
  });
  try {
    // A read sees every earlier write from this page.
    const read = pendingWrites.then(() => readStoredPreference(factory));
    return await Promise.race([read, bound]);
  } finally {
    clearTimeout(timer);
  }
}

async function readStoredPreference(factory: IDBFactory): Promise<number> {
  try {
    const database = await openDatabase(factory);
    try {
      const value = await new Promise<unknown>((resolve, reject) => {
        const request = database.transaction(STORE_NAME, "readonly")
          .objectStore(STORE_NAME).get(MONITOR_VOLUME_KEY);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      // Invalid storage falls back to the same default as a new device.
      return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 100 ? value : 100;
    } finally {
      database.close();
    }
  } catch {
    return 100;
  }
}

// Resolves once the write has committed, or when it could not be stored.
// Writes run one after another, so the last call is the one remembered
// whichever of their connections opens first.
export function writeMonitorVolumePreference(
  value: number,
  factory: IDBFactory | null = defaultFactory(),
): Promise<void> {
  if (!Number.isFinite(value) || value < 0 || value > 100) throw new TypeError("Invalid monitor volume");
  const write = pendingWrites.then(() => storePreference(value, factory));
  pendingWrites = write;
  return write;
}

async function storePreference(
  value: number,
  factory: IDBFactory | null,
): Promise<void> {
  if (factory === null) return;
  try {
    const database = await openDatabase(factory);
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put(value, MONITOR_VOLUME_KEY);
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
