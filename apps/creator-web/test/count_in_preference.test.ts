import {IDBFactory} from "fake-indexeddb";
import {expect, test, vi} from "vitest";

import {
  type CountInBars,
  readCountInPreference,
  writeCountInPreference,
} from "../src/state/count_in_preference";
import {readSeqSnapPreference} from "../src/state/seq_snap_preference";

// Raw access is independent of the module's key/decoder. A round-trip through
// two functions sharing a wrong key or string encoding would otherwise pass.
async function openRawSettings(factory: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = factory.open("lmdj.creator.host", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("settings");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function putRawSetting(factory: IDBFactory, key: string, value: unknown): Promise<void> {
  const database = await openRawSettings(factory);
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction("settings", "readwrite");
      transaction.objectStore("settings").put(value, key);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

async function readRawSetting(factory: IDBFactory, key: string): Promise<unknown> {
  const database = await openRawSettings(factory);
  try {
    return await new Promise((resolve, reject) => {
      const request = database.transaction("settings", "readonly")
        .objectStore("settings").get(key);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  } finally {
    database.close();
  }
}

// The stub separates put acceptance from transaction settlement. Real IndexedDB
// persistence/encoding is exercised above; this seam only controls that ordering.
function controlledWrite() {
  const put = vi.fn();
  const transaction = {
    objectStore: () => ({put}),
    error: new DOMException("Storage transaction aborted", "AbortError"),
  } as unknown as IDBTransaction;
  const close = vi.fn();
  const database = {
    transaction: () => transaction,
    close,
  } as unknown as IDBDatabase;
  const request = {result: database} as unknown as IDBOpenDBRequest;
  const factory = {
    open: () => {
      queueMicrotask(() => request.onsuccess?.(new Event("success")));
      return request;
    },
  } as unknown as IDBFactory;
  return {factory, transaction, put, close};
}

test("a missing preference defaults to Off", async () => {
  expect(await readCountInPreference(new IDBFactory())).toBe(0);
});

test("unavailable IndexedDB defaults to Off and accepts a best-effort write", async () => {
  expect(await readCountInPreference(null)).toBe(0);
  await expect(writeCountInPreference(2, null)).resolves.toBeUndefined();
});

test.each([0, 1, 2] as const)("choice %i is stored as a number at the approved key", async (bars) => {
  const factory = new IDBFactory();
  await writeCountInPreference(bars, factory);
  expect(await readRawSetting(factory, "count-in.v1")).toBe(bars);
  expect(await readCountInPreference(factory)).toBe(bars);
});

test.each([0, 1, 2] as const)("reads numeric choice %i from an existing database", async (bars) => {
  const factory = new IDBFactory();
  await putRawSetting(factory, "count-in.v1", bars);
  expect(await readCountInPreference(factory)).toBe(bars);
});

test.each(["0", "1", "2", true, null, -1, 3, 0.5])(
  "corrupt stored value %j defaults to Off",
  async (value) => {
    const factory = new IDBFactory();
    await putRawSetting(factory, "count-in.v1", value);
    expect(await readCountInPreference(factory)).toBe(0);
  },
);

test("a read after rapid writes observes the last committed choice", async () => {
  const factory = new IDBFactory();
  const one = writeCountInPreference(1, factory);
  const two = writeCountInPreference(2, factory);
  const off = writeCountInPreference(0, factory);
  const latest = readCountInPreference(factory);
  expect(await latest).toBe(0);
  await Promise.all([one, two, off]);
  expect(await readRawSetting(factory, "count-in.v1")).toBe(0);
});

test("writes preserve the other Host settings and stay local to this device", async () => {
  const factory = new IDBFactory();
  await putRawSetting(factory, "seq-snap.v1", "beat");
  await putRawSetting(factory, "metronome.v1", true);
  await writeCountInPreference(2, factory);
  expect(await readSeqSnapPreference(factory)).toBe("beat");
  expect(await readRawSetting(factory, "metronome.v1")).toBe(true);
  expect(await readCountInPreference(new IDBFactory())).toBe(0);
});

test("a failed database open falls back to Off without poisoning subsequent writes", async () => {
  const blocked = {
    open: () => { throw new Error("storage blocked"); },
  } as unknown as IDBFactory;
  expect(await readCountInPreference(blocked)).toBe(0);
  await expect(writeCountInPreference(1, blocked)).resolves.toBeUndefined();
  const working = new IDBFactory();
  await writeCountInPreference(2, working);
  expect(await readCountInPreference(working)).toBe(2);
});

test("a read whose database open never settles returns Off at its boot bound", async () => {
  const stuck = {open: () => ({})} as unknown as IDBFactory;
  expect(await readCountInPreference(stuck, 10)).toBe(0);
});

test("put acceptance does not settle the write before transaction completion", async () => {
  const controlled = controlledWrite();
  let settled = false;
  const write = writeCountInPreference(1, controlled.factory).then(() => { settled = true; });
  // Observe the actual put before checking absence; an assertion made before
  // the async chain started would pass even if it resolved at put acceptance.
  await vi.waitFor(() => expect(controlled.put).toHaveBeenCalledWith(1, "count-in.v1"));
  expect(settled).toBe(false);
  controlled.transaction.oncomplete?.(new Event("complete"));
  await write;
  expect(settled).toBe(true);
  expect(controlled.close).toHaveBeenCalledOnce();
});

test("an earlier unsettled write cannot hold a boot read past its bound", async () => {
  const controlled = controlledWrite();
  const write = writeCountInPreference(1, controlled.factory);
  await vi.waitFor(() => expect(controlled.put).toHaveBeenCalledOnce());
  try {
    expect(await readCountInPreference(controlled.factory, 10)).toBe(0);
  } finally {
    controlled.transaction.oncomplete?.(new Event("complete"));
    await write;
  }
});

test("an aborted transaction releases the write queue for a later choice", async () => {
  const controlled = controlledWrite();
  const write = writeCountInPreference(1, controlled.factory);
  await vi.waitFor(() => expect(controlled.put).toHaveBeenCalledOnce());
  controlled.transaction.onabort?.(new Event("abort"));
  await expect(write).resolves.toBeUndefined();
  expect(controlled.close).toHaveBeenCalledOnce();
  const working = new IDBFactory();
  await writeCountInPreference(2, working);
  expect(await readCountInPreference(working)).toBe(2);
});

test.each(["1", -1, 3, 0.5, NaN, Infinity, null, undefined])(
  "rejects invalid write %j before entering the storage queue",
  (value) => {
    expect(() => writeCountInPreference(value as CountInBars, new IDBFactory()))
      .toThrow(TypeError);
  },
);
