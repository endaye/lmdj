# Portal Witness Existing-File Error Implementation Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Architecture Portal witness command reject an existing witness with a stable error that names the exact existing witness, without overwriting it.

**Architecture:** Keep witness creation and the exclusive-create filesystem contract in `create-squash-witness.mjs`. The entrypoint will translate only Node's `EEXIST` rejection from `writeFile(..., {flag: 'wx'})` into an operator-facing error; every other failure remains unchanged. The Portal regression test will execute the real entrypoint in an isolated fixture twice and assert both its output and byte-for-byte witness preservation.

**Tech Stack:** Node.js ESM, `node:test`, `node:fs/promises`, Git fixture repositories, Bash Portal check.

## Global Constraints

- Work only on `fix/portal-witness-existing` in `/Users/endaye/Projects/lmdj/.worktrees/issue-209-portal-witness`; never modify `main`.
- Preserve `writeFile(output, bytes, {flag: 'wx'})`: an existing witness must reject and must never be overwritten.
- The expected tracked files are exactly this plan, `apps/architecture-portal/scripts/create-squash-witness.mjs`, and `apps/architecture-portal/test/snapshot-provenance.test.mjs`.
- Do not push, open a Pull Request, merge, close Issue #209, tag, release, deploy, or promote a Channel.
- Run `node --test apps/architecture-portal/test/snapshot-provenance.test.mjs` and `scripts/architecture-portal.sh check` before committing.

## Version Management

Version impact: none. This changes only local command diagnostics for an already-rejected exclusive witness write; no Product Build, Assembly, Core Module, Provider, Host, or Contract identity changes.

## Documentation impact

Documentation impact: none. No Portal page, source diagram, product capability, identity, or release procedure changes; this plan is the required implementation record and the command's stable diagnostic is covered by automated test.

## File Structure

- Create: `docs/plans/2026-08-20-lmdj-portal-witness-existing-file-error.md` — bounded TDD implementation record and acceptance criteria.
- Modify: `apps/architecture-portal/test/snapshot-provenance.test.mjs` — integration regression for first witness creation and second exclusive-write rejection.
- Modify: `apps/architecture-portal/scripts/create-squash-witness.mjs` — translates only `EEXIST` to the named, stable diagnostic while retaining `{flag: 'wx'}`.

### Task 1: Reproduce the Witness Collision

**Files:**
- Test: `apps/architecture-portal/test/snapshot-provenance.test.mjs`

**Interfaces:**
- Consumes: `node scripts/create-squash-witness.mjs PRODUCT_BUILD INTRODUCING_REVISION` in a fixture repository containing its Portal script and provenance library.
- Produces: an integration test that proves the first command creates `version-1.0.14.0-squash-witness.json`, and a second command rejects while preserving its original bytes.

- [ ] **Step 1: Write the failing test**

Add a test that copies the real witness entrypoint and provenance library into `initializeFixture()`'s temporary repository, creates the snapshot metadata, and invokes the entrypoint twice. Capture the first witness bytes and assert the second invocation exits non-zero with:

```js
assert.match(second.stderr, new RegExp(
  `squash witness already exists: apps/architecture-portal/versioned_provenance/version-${VERSION}-squash-witness\\.json`,
));
assert.deepEqual(await readFile(output), firstBytes);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test apps/architecture-portal/test/snapshot-provenance.test.mjs`

Expected: FAIL in the new test because the current second invocation exposes Node's raw `EEXIST` rejection rather than the stable named witness diagnostic; all pre-existing tests remain green.

### Task 2: Translate Only the Exclusive-Create Collision

**Files:**
- Modify: `apps/architecture-portal/scripts/create-squash-witness.mjs`
- Test: `apps/architecture-portal/test/snapshot-provenance.test.mjs`

**Interfaces:**
- Consumes: the `Error` rejected by `writeFile(output, witnessBytes, {flag: 'wx'})`.
- Produces: stderr `portal squash witness already exists: <repo-relative witness path>` and exit status 1 on `error.code === 'EEXIST'`; non-`EEXIST` errors still reject unchanged.

- [ ] **Step 1: Write minimal implementation**

Wrap only the exclusive write and keep the exact `wx` option:

```js
try {
  await writeFile(output, `${JSON.stringify(witness, null, 2)}\\n`, {flag: 'wx'});
} catch (error) {
  if (error?.code !== 'EEXIST') throw error;
  console.error(`portal squash witness already exists: ${path.relative(repoRoot, output)}`);
  process.exitCode = 1;
}
if (process.exitCode !== 1) console.log(`portal squash witness: ${path.relative(repoRoot, output)}`);
```

- [ ] **Step 2: Run test to verify it passes**

Run: `node --test apps/architecture-portal/test/snapshot-provenance.test.mjs`

Expected: PASS with the new test and all existing snapshot-provenance tests green.

- [ ] **Step 3: Run complete task verification**

Run:

```bash
node --test apps/architecture-portal/test/snapshot-provenance.test.mjs
scripts/architecture-portal.sh check
```

Expected: both exit 0; the Portal check completes all validation, typecheck, build, and build-check gates.

- [ ] **Step 4: Inspect and commit the atomic Task**

Run:

```bash
git branch --show-current
git add docs/plans/2026-08-20-lmdj-portal-witness-existing-file-error.md \\
  apps/architecture-portal/scripts/create-squash-witness.mjs \\
  apps/architecture-portal/test/snapshot-provenance.test.mjs
git diff --cached --name-status
git diff --cached --check
git diff --cached
git commit -m "fix(portal): name existing squash witness error"
git show --stat --oneline --summary HEAD
git status --short
```

Expected: the branch is not `main`; exactly the three declared files are committed; the staged diff has no whitespace errors; the final worktree is clean; no remote mutation occurs.

## Acceptance Criteria

- A first witness invocation creates the witness file successfully.
- A second invocation against the same output exits non-zero, prints a stable error naming the existing repository-relative witness path, and does not expose an unhandled `EEXIST` stack or overwrite the file.
- The exclusive-create `{flag: 'wx'}` contract remains present in production code.
- The focused Portal test and full `scripts/architecture-portal.sh check` both pass.
