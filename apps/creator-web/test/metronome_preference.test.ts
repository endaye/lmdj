import {IDBFactory} from "fake-indexeddb";
import {expect, test} from "vitest";

import {
  readMetronomePreference,
  writeMetronomePreference,
} from "../src/state/metronome_preference";

const DATABASE_NAME = "lmdj.creator.host";
const STORE_NAME = "settings";
const METRONOME_KEY = "metronome.v1";

// Writes a raw value under the preference key, bypassing the module, the way
// a corrupted store would present it.
async function corruptStoredValue(factory: IDBFactory): Promise<void> {
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
      transaction.objectStore(STORE_NAME).put("yes", METRONOME_KEY);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error);
    });
  } finally {
    database.close();
  }
}

test("an absent preference reads as off", async () => {
  expect(await readMetronomePreference()).toBe(false);
  expect(await readMetronomePreference(new IDBFactory())).toBe(false);
});

test("a written preference reads back on the same store", async () => {
  const factory = new IDBFactory();
  await writeMetronomePreference(true, factory);
  expect(await readMetronomePreference(factory)).toBe(true);
  await writeMetronomePreference(false, factory);
  expect(await readMetronomePreference(factory)).toBe(false);
  // Another device's store never sees this device's preference.
  expect(await readMetronomePreference(new IDBFactory())).toBe(false);
});

test("a corrupted stored value reads as off", async () => {
  const factory = new IDBFactory();
  await corruptStoredValue(factory);
  expect(await readMetronomePreference(factory)).toBe(false);
});
