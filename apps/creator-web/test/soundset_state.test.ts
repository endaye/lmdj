import {expect, test} from "vitest";

import {
  initialSoundSetState,
  reduceSoundSet,
  selectCanInstall,
  selectPadPlan,
  selectWriteCount,
  type SoundSetState,
} from "../src/state/soundset_state";
import type {
  SoundSetInstallReceipt,
  SoundSetMapPreview,
} from "../src/runtime/runtime_types";

const IDENTITY = {
  setId: "11111111-1111-4111-8111-111111111111",
  version: "1.0.0",
  manifestSha256: "a1".repeat(32),
};

function preview(
  overrides: Partial<SoundSetMapPreview> = {},
): SoundSetMapPreview {
  return {
    ...IDENTITY,
    bankId: 0,
    projectRevision: 4,
    proposed: [0, 1, 2].map((pad) => ({
      slotIndex: pad,
      pad,
      artifact: {sha256: "b2".repeat(32), mediaType: "audio/wav", byteLength: 64},
    })),
    // `map_soundset` reports every empty Set slot as kept.
    collisions: [],
    kept: [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    ...overrides,
  };
}

const withPreview = (value: SoundSetMapPreview): SoundSetState =>
  reduceSoundSet(initialSoundSetState, {type: "previewed", preview: value});

test("a mapping with no collision installs on confirmation alone", () => {
  const state = withPreview(preview());
  expect(state.policy).toBeNull();
  expect(selectCanInstall(state)).toBe(true);
  expect(selectWriteCount(state)).toBe(3);
});

test("a mapping with collisions cannot be submitted without keep or replace", () => {
  const state = withPreview(preview({collisions: [1, 2]}));
  expect(selectCanInstall(state)).toBe(false);
  // No count is announced under a policy the user has not chosen.
  expect(selectWriteCount(state)).toBeNull();

  const keep = reduceSoundSet(state, {type: "policy-selected", policy: "keep"});
  expect(selectCanInstall(keep)).toBe(true);
  // `keep` writes only the Pads that were free.
  expect(selectWriteCount(keep)).toBe(1);

  const replace = reduceSoundSet(state, {
    type: "policy-selected",
    policy: "replace",
  });
  expect(selectCanInstall(replace)).toBe(true);
  expect(selectWriteCount(replace)).toBe(3);
});

test("a fresh mapping drops a policy chosen against the previous one", () => {
  const chosen = reduceSoundSet(
    withPreview(preview({collisions: [1]})),
    {type: "policy-selected", policy: "replace"},
  );
  expect(chosen.policy).toBe("replace");

  const remapped = reduceSoundSet(chosen, {
    type: "previewed",
    preview: preview({bankId: 2, collisions: [4]}),
  });
  expect(remapped.policy).toBeNull();
  expect(selectCanInstall(remapped)).toBe(false);
});

test("changing the target Bank drops the mapping it was made against", () => {
  const state = reduceSoundSet(
    withPreview(preview({collisions: [1]})),
    {type: "bank-selected", bank: 3},
  );
  expect(state.preview).toBeNull();
  expect(state.policy).toBeNull();
  expect(selectCanInstall(state)).toBe(false);
});

test("a Pad the mapping did not classify is not reported as untouched", () => {
  // `kept` is Core's own answer for "the Set has nothing for this Pad". A Pad
  // that is in neither list is a mapping this Host does not understand, and
  // showing it as untouched would be the S11-D12 mistake in reverse.
  const plan = selectPadPlan(withPreview(preview({kept: [3, 4]})));
  expect(plan.filter((entry) => entry.plan === "empty-in-set").map((e) => e.pad))
    .toEqual([3, 4]);
  expect(plan.filter((entry) => entry.plan === "unclassified")).toHaveLength(11);
});

test("an empty Set slot is a Pad the mapping leaves alone, never a write", () => {
  const plan = selectPadPlan(withPreview(preview({collisions: [1]})));
  expect(plan.filter((entry) => entry.plan === "install").map((e) => e.pad))
    .toEqual([0, 2]);
  expect(plan.filter((entry) => entry.plan === "collision").map((e) => e.pad))
    .toEqual([1]);
  // Thirteen empty Set slots, and none of them is a write of any kind.
  expect(plan.filter((entry) => entry.plan === "empty-in-set")).toHaveLength(13);
});

test("an install receipt replaces the mapping it was confirmed against", () => {
  const receipt: SoundSetInstallReceipt = {
    ...IDENTITY,
    bankId: 0,
    committedRevision: 5,
    replayed: false,
    installed: [{slotIndex: 0, pad: 0}],
    collisions: [],
    kept: [],
  };
  const state = reduceSoundSet(withPreview(preview()), {
    type: "installed",
    receipt,
  });
  expect(state.receipt).toBe(receipt);
  expect(state.preview).toBeNull();
  expect(selectCanInstall(state)).toBe(false);
});

test("a Catalog that never answered is not a Catalog that is unreachable", () => {
  expect(initialSoundSetState.catalogAvailable).toBeNull();
  const listed = reduceSoundSet(initialSoundSetState, {
    type: "listed",
    catalog: {catalogAvailable: false, sets: [], refused: []},
  });
  expect(listed.catalogAvailable).toBe(false);
});
