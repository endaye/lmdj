import {IDBFactory} from "fake-indexeddb";
import {expect, test} from "vitest";

import {
  readSeqSnapPreference,
  writeSeqSnapPreference,
} from "../src/state/seq_snap_preference";

const DATABASE_NAME = "lmdj.creator.host";
const STORE_NAME = "settings";
const SEQ_SNAP_KEY = "seq-snap.v1";

// Writes a raw value under the preference key, bypassing the module, the way
// a corrupted store would present it.
async function corruptStoredValue(factory: IDBFactory, value: unknown): Promise<void> {
  const database = await new Promise<IDBDatabase>((resolve, reject) => {
    const request = factory.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(value, SEQ_SNAP_KEY);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

test("an absent or unavailable preference reads as 1 BAR", async () => {
  expect(await readSeqSnapPreference()).toBe("bar");
  expect(await readSeqSnapPreference(new IDBFactory())).toBe("bar");
  expect(await readSeqSnapPreference(null)).toBe("bar");
});

test("each snap round-trips on the same store", async () => {
  const factory = new IDBFactory();
  for (const snap of ["beat", "bar", "pattern_end"] as const) {
    await writeSeqSnapPreference(snap, factory);
    expect(await readSeqSnapPreference(factory)).toBe(snap);
  }
  // Another device's store never sees this device's preference.
  expect(await readSeqSnapPreference(new IDBFactory())).toBe("bar");
});

// Writes serialize, so the last of two rapid choices is the one a later read
// observes; a user's latest selection cannot be lost to an earlier write.
test("rapid writes keep the last choice", async () => {
  const factory = new IDBFactory();
  await writeSeqSnapPreference("bar", factory);
  const beat = writeSeqSnapPreference("beat", factory);
  const end = writeSeqSnapPreference("pattern_end", factory);
  await Promise.all([beat, end]);
  expect(await readSeqSnapPreference(factory)).toBe("pattern_end");
});

test.each(["sometimes", 3, true, null])(
  "a corrupted stored value %j reads as 1 BAR",
  async (value) => {
    const factory = new IDBFactory();
    await corruptStoredValue(factory, value);
    expect(await readSeqSnapPreference(factory)).toBe("bar");
  },
);

test("an unreadable store reads as 1 BAR", async () => {
  const failing = {
    open: () => {
      throw new Error("storage blocked");
    },
  } as unknown as IDBFactory;
  expect(await readSeqSnapPreference(failing)).toBe("bar");
});

test("a store that never settles does not hold boot past the bound", async () => {
  const stuck = {open: () => ({})} as unknown as IDBFactory;
  expect(await readSeqSnapPreference(stuck, 10)).toBe("bar");
});

test("write refuses a value outside the snap union", () => {
  const factory = new IDBFactory();
  expect(() => writeSeqSnapPreference("off" as never, factory)).toThrow(TypeError);
});
