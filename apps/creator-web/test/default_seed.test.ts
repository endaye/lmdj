import {expect, test} from "vitest";
import {claimDefaultSeed, readDefaultSeed, saveDefaultSeed, DEFAULT_SEED_KEY, type SeedStorage} from "../src/state/default_seed";
const identity = {setId: "11111111-1111-4111-8111-111111111111", version: "1.0.0", manifestSha256: "a".repeat(64)};
const projectId = "22222222-2222-4222-8222-222222222222";
function storage(): SeedStorage {const values = new Map<string,string>();return {getItem: key => values.get(key) ?? null, setItem: (key,value) => {values.set(key,value);}};}
test("first claim persists sixteen owned slots and never claims another Project", () => {
  const store = storage();
  const first = claimDefaultSeed(store, identity, projectId);
  expect(first?.slots).toHaveLength(16);
  expect(readDefaultSeed(store, identity)?.projectId).toBe(projectId);
  expect(claimDefaultSeed(store, identity, "33333333-3333-4333-8333-333333333333")).toBeNull();
});
test("invalid retained journal refuses a fresh automatic claim", () => {
  const store = storage(); store.setItem(DEFAULT_SEED_KEY, "{}");
  expect(() => claimDefaultSeed(store, identity, projectId)).toThrow("invalid");
  expect(store.getItem(DEFAULT_SEED_KEY)).toBe("{}");
});
test("persisted terminal ownership remains terminal after reload", () => {
  const store = storage(); const seed = claimDefaultSeed(store, identity, projectId)!;
  seed.slots[0]!.phase = "ready";
  store.setItem(DEFAULT_SEED_KEY, JSON.stringify(seed));
  expect(readDefaultSeed(store, identity)?.slots[0]?.phase).toBe("ready");
  expect(claimDefaultSeed(store, identity, projectId)).toBeNull();
});

test("assignment history persists without invalidating an older journal", () => {
  const store = storage(); const seed = claimDefaultSeed(store, identity, projectId)!;
  expect(readDefaultSeed(store, identity)?.slots[0]?.assignmentObserved).toBeUndefined();
  seed.slots[0]!.assignmentObserved = true;
  saveDefaultSeed(store, seed);
  expect(readDefaultSeed(store, identity)?.slots[0]?.assignmentObserved).toBe(true);
});

test("an invalid assignment marker preserves the journal and refuses a new claim", () => {
  const store = storage(); const seed = claimDefaultSeed(store, identity, projectId)!;
  const raw = JSON.stringify({...seed, slots: seed.slots.map((slot, index) =>
    index === 0 ? {...slot, assignmentObserved: "true"} : slot)});
  store.setItem(DEFAULT_SEED_KEY, raw);
  expect(() => claimDefaultSeed(store, identity, projectId)).toThrow("invalid");
  expect(store.getItem(DEFAULT_SEED_KEY)).toBe(raw);
});
