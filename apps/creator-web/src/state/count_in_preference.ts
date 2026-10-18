// COUNT-IN is a device preference for global Pattern Record, never Project
// Truth. Store numeric Off / 1 / 2 in the existing Host settings database;
// missing, corrupt or unavailable storage reads as Off. The consuming App
// must separately guard late hydration against a newer user choice.
export type CountInBars = 0 | 1 | 2;

const DATABASE_NAME = "lmdj.creator.host";
const DATABASE_VERSION = 1;
const STORE_NAME = "settings";
const COUNT_IN_KEY = "count-in.v1";
const DEFAULT_COUNT_IN: CountInBars = 0;
const READ_BOUND_MS = 5_000;

function isCountInBars(value: unknown): value is CountInBars {
  return value === 0 || value === 1 || value === 2;
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
      database.onversionchange = () => database.close();
      resolve(database);
    };
    request.onerror = () => reject(request.error);
  });
}

let pendingWrites: Promise<void> = Promise.resolve();

export async function readCountInPreference(
  factory: IDBFactory | null = defaultFactory(),
  boundMs = READ_BOUND_MS,
): Promise<CountInBars> {
  if (factory === null) return DEFAULT_COUNT_IN;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const bound = new Promise<CountInBars>((resolve) => {
    timer = setTimeout(() => resolve(DEFAULT_COUNT_IN), boundMs);
  });
  try {
    // Observe earlier choices from this page, with a bounded boot fallback if
    // either a write or the read's open never settles.
    const read = pendingWrites.then(() => readStoredPreference(factory));
    return await Promise.race([read, bound]);
  } finally {
    clearTimeout(timer);
  }
}

async function readStoredPreference(factory: IDBFactory): Promise<CountInBars> {
  try {
    const database = await openDatabase(factory);
    try {
      const value = await new Promise<unknown>((resolve, reject) => {
        const request = database.transaction(STORE_NAME, "readonly")
          .objectStore(STORE_NAME).get(COUNT_IN_KEY);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      return isCountInBars(value) ? value : DEFAULT_COUNT_IN;
    } finally {
      database.close();
    }
  } catch {
    return DEFAULT_COUNT_IN;
  }
}

// Serialized writes preserve the latest choice. Completion means the
// transaction committed or storage failed, not merely that put was accepted.
export function writeCountInPreference(
  bars: CountInBars,
  factory: IDBFactory | null = defaultFactory(),
): Promise<void> {
  if (!isCountInBars(bars)) throw new TypeError("Invalid count-in bars");
  const write = pendingWrites.then(() => storePreference(bars, factory));
  pendingWrites = write;
  return write;
}

async function storePreference(
  bars: CountInBars,
  factory: IDBFactory | null,
): Promise<void> {
  if (factory === null) return;
  try {
    const database = await openDatabase(factory);
    try {
      await new Promise<void>((resolve, reject) => {
        const transaction = database.transaction(STORE_NAME, "readwrite");
        transaction.objectStore(STORE_NAME).put(bars, COUNT_IN_KEY);
        transaction.oncomplete = () => resolve();
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
    } finally {
      database.close();
    }
  } catch {
    // Storage failure leaves the in-memory choice usable; it must not poison
    // the queue and prevent a later choice from being remembered.
  }
}
