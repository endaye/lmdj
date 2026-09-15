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

test("both accepted families name only levels the Contract declares", () => {
  for (const level of [
    ...PATTERN_FREE_PROJECT_CONTRACTS,
    ...PATTERN_SLOT_PROJECT_CONTRACTS,
  ]) {
    expect(CONTRACT_LEVELS).toContain(level);
  }
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
