import {readMetronomePreference} from "../src/state/metronome_preference";
import {IDBFactory} from "fake-indexeddb";
import {expect, test} from "vitest";
import {readMonitorVolumePreference, writeMonitorVolumePreference} from "../src/state/monitor_volume_preference";

test("device volume defaults to 100 and remembers zero across a new read", async () => {
  const factory = new IDBFactory();
  expect(await readMonitorVolumePreference(factory)).toBe(100);
  await writeMonitorVolumePreference(0, factory);
  expect(await readMonitorVolumePreference(factory)).toBe(0);
  expect(await readMonitorVolumePreference(new IDBFactory())).toBe(100);
  expect(await readMonitorVolumePreference(null)).toBe(100);
});

test("serialized volume writes keep the last turn and reject invalid levels", async () => {
  const factory = new IDBFactory();
  await Promise.all([writeMonitorVolumePreference(20, factory), writeMonitorVolumePreference(75, factory)]);
  expect(await readMonitorVolumePreference(factory)).toBe(75);
  expect(() => writeMonitorVolumePreference(-1, factory)).toThrow();
  expect(() => writeMonitorVolumePreference(NaN, factory)).toThrow();
});

test("an open that never settles has a bounded default", async () => {
  const factory = {open: () => ({})} as unknown as IDBFactory;
  expect(await readMonitorVolumePreference(factory, 1)).toBe(100);
});

test("corrupt volume falls back without changing other Host settings", async () => {
  const factory = new IDBFactory();
  await writeMonitorVolumePreference(50, factory);
  const database = await new Promise<IDBDatabase>((resolve) => {
    const request = factory.open("lmdj.creator.host", 1);
    request.onsuccess = () => resolve(request.result);
  });
  await new Promise<void>((resolve) => {
    const transaction = database.transaction("settings", "readwrite");
    transaction.objectStore("settings").put("50", "monitor-volume.v1");
    transaction.objectStore("settings").put(true, "metronome.v1");
    transaction.oncomplete = () => resolve();
  });
  database.close();
  expect(await readMonitorVolumePreference(factory)).toBe(100);
  expect(await readMetronomePreference(factory)).toBe(true);
});
