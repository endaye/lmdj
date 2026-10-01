import {IDBFactory} from "fake-indexeddb";
import {expect, test} from "vitest";

import {readLastProjectId, writeLastProjectId} from "../src/state/last_project";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";
const LATER_ID = "33333333-3333-4333-8333-333333333333";

test("a written Project identity reads back", async () => {
  await writeLastProjectId(PROJECT_ID);
  expect(await readLastProjectId()).toBe(PROJECT_ID);
});

test("a Project identity survives a new connection to the same store", async () => {
  const factory = new IDBFactory();
  await writeLastProjectId(PROJECT_ID, factory);
  expect(await readLastProjectId(factory)).toBe(PROJECT_ID);
  expect(await readLastProjectId(new IDBFactory())).toBeNull();
});

// Holds back the first open's success, as a slow connection would.
function slowFirstOpen(inner: IDBFactory, delayMs: number): IDBFactory {
  let opens = 0;
  return {
    open(name: string, version?: number) {
      const request = inner.open(name, version);
      if (opens++ > 0) return request;
      const delayed: Record<string, unknown> = {
        onupgradeneeded: null, onsuccess: null, onerror: null,
      };
      Object.defineProperty(delayed, "result", {get: () => request.result});
      Object.defineProperty(delayed, "error", {get: () => request.error});
      const forward = (name: string) => (event: Event) =>
        (delayed[name] as ((event: Event) => void) | null)?.(event);
      request.onupgradeneeded = forward("onupgradeneeded");
      request.onerror = forward("onerror");
      request.onsuccess = (event) => {
        setTimeout(() => forward("onsuccess")(event), delayMs);
      };
      return delayed as unknown as IDBOpenDBRequest;
    },
  } as unknown as IDBFactory;
}

test("the later of two writes is remembered even when its connection opens first", async () => {
  const slow = slowFirstOpen(indexedDB, 50);
  const first = writeLastProjectId(PROJECT_ID, slow);
  const second = writeLastProjectId(LATER_ID, slow);
  await Promise.all([first, second]);
  expect(await readLastProjectId()).toBe(LATER_ID);
});

test("a read issued while a write is pending sees that write", async () => {
  const write = writeLastProjectId(PROJECT_ID, slowFirstOpen(indexedDB, 50));
  expect(await readLastProjectId()).toBe(PROJECT_ID);
  await write;
});

test("a read whose open never settles counts as nothing remembered", async () => {
  const hanging = {open: () => ({})} as unknown as IDBFactory;
  expect(await readLastProjectId(hanging, 20)).toBeNull();
});

test("a stored value that is not a Project identity reads as none", async () => {
  await new Promise<void>((resolve, reject) => {
    const request = indexedDB.open("lmdj.creator.host", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("settings");
    request.onerror = () => reject(request.error);
    request.onsuccess = () => {
      const transaction = request.result.transaction("settings", "readwrite");
      transaction.objectStore("settings").put("not-a-uuid", "last-project.v1");
      transaction.oncomplete = () => { request.result.close(); resolve(); };
    };
  });
  expect(await readLastProjectId()).toBeNull();
});

test("an invalid identity is never written", async () => {
  await writeLastProjectId("not-a-uuid");
  expect(await readLastProjectId()).toBeNull();
});

test("unusable storage reads as none and never rejects on write", async () => {
  const broken = {
    open: () => { throw new Error("denied"); },
  } as unknown as IDBFactory;
  expect(await readLastProjectId(broken)).toBeNull();
  await expect(writeLastProjectId(PROJECT_ID, broken)).resolves.toBeUndefined();
  expect(await readLastProjectId(null)).toBeNull();
});
