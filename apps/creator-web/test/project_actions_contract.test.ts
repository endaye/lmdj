import {readFileSync} from "node:fs";
import {resolve} from "node:path";

import {expect, test} from "vitest";

import {
  PATTERN_FREE_PROJECT_CONTRACTS,
  PATTERN_SLOT_PROJECT_CONTRACTS,
} from "../src/runtime/project_actions";

interface BundleSchema {
  properties: {project_contract: {enum: string[]}};
}

// vitest runs this suite with apps/creator-web as the working directory.
const BUNDLE_SCHEMA = JSON.parse(readFileSync(
  resolve(
    process.cwd(),
    "../../contracts/project/lmdj.project-bundle.v1.schema.json",
  ),
  "utf-8",
)) as BundleSchema;

// The Project Contract levels a Bundle may name, read off the Contract rather
// than retyped -- retyping is the habit that kept #784, #900 and #915 green
// through a level move.
const CONTRACT_LEVELS: readonly string[] =
  BUNDLE_SCHEMA.properties.project_contract.enum;
const contractLevel = (contract: string) =>
  Number(contract.slice("lmdj.project.v".length));
// The writer emits the current, highest declared level.
const WRITER_PROJECT_CONTRACT = CONTRACT_LEVELS.reduce((highest, level) =>
  contractLevel(level) > contractLevel(highest) ? level : highest);

// The Bundle envelope declares only the writer's current level (#1364), but
// legacy v3/v4 Project Truth remains loadable through structural parsing and
// keeps its level identity until promoted on persist
// (docs/prd/decisions/2026-09-15-project-bundle-current-level-only.md), so a
// reader must still accept exactly those legacy levels. Pinning the set makes
// any future legacy-loading change an explicit, test-visible decision.
const LEGACY_LOADABLE_LEVELS: readonly string[] =
  Object.freeze(["lmdj.project.v3", "lmdj.project.v4"]);

test("the families name exactly the writer level plus the legacy loadable levels", () => {
  const accepted = [
    ...PATTERN_FREE_PROJECT_CONTRACTS,
    ...PATTERN_SLOT_PROJECT_CONTRACTS,
  ].sort();
  const expected = [WRITER_PROJECT_CONTRACT, ...LEGACY_LOADABLE_LEVELS].sort();
  expect(accepted).toEqual(expected);
});

test("the families claim disjoint levels", () => {
  for (const level of PATTERN_FREE_PROJECT_CONTRACTS) {
    expect(PATTERN_SLOT_PROJECT_CONTRACTS).not.toContain(level);
  }
});

test("accepts the Project Contract level this Build's writer produces", () => {
  // A level move that leaves the writer's level unaccepted refuses every
  // Project the Build creates -- #900's failure one function downstream.
  expect(PATTERN_SLOT_PROJECT_CONTRACTS).toContain(WRITER_PROJECT_CONTRACT);
});
