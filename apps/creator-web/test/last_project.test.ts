import {expect, test} from "vitest";

import {
  readLastProjectId,
  writeLastProjectId,
  type LastProjectStorage,
} from "../src/state/last_project";

const PROJECT_ID = "11111111-1111-4111-8111-111111111111";

function memoryStorage(): LastProjectStorage & {values: Map<string, string>} {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
  };
}

test("a written Project identity reads back", () => {
  const storage = memoryStorage();
  writeLastProjectId(PROJECT_ID, storage);
  expect(readLastProjectId(storage)).toBe(PROJECT_ID);
});

test("a stored value that is not a Project identity reads as none", () => {
  const storage = memoryStorage();
  storage.setItem("lmdj.creator.last-project.v1", "not-a-uuid");
  expect(readLastProjectId(storage)).toBeNull();
});

test("an invalid identity is never written", () => {
  const storage = memoryStorage();
  writeLastProjectId("not-a-uuid", storage);
  expect(storage.values.size).toBe(0);
});

test("unusable storage reads as none and never throws on write", () => {
  const broken: LastProjectStorage = {
    getItem: () => { throw new Error("denied"); },
    setItem: () => { throw new Error("quota"); },
  };
  expect(readLastProjectId(broken)).toBeNull();
  expect(() => writeLastProjectId(PROJECT_ID, broken)).not.toThrow();
});
