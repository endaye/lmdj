# Retained-source witness verification for release recovery

Delivery base: e73eeac0f047d047c4a3881c72ea235b537282fa.

## Task

Add `scripts/docs-site.sh verify-witness PRODUCT_BUILD INTRODUCING_REVISION`.
The existing generator is create-only; recovery must verify an existing result
without invoking another write. Bind the explicit introducing revision to the
official metadata-introduction resolver, require checked-out metadata bytes to
match that commit, then compare existing witness bytes with the official
deterministic generator's expected bytes. Emit a JSON receipt with exact path,
byte length and SHA-256. Never create/replace a witness or change Git refs/index.

This is retained-source producer-side verification, not the fresh-clone consumer,
full snapshot provenance, actual main/review authority, or candidate completion.
The caller must retain the source object, authenticate candidate/source/Task and
own an immutable checkout during the command. Durable command enrollment,
unknown-attempt recovery, witness Task/PR and release-parent wiring follow this
prerequisite; no signing, release, GitHub write or deployment is in this Task.

## Declared files

- scripts/docs-site.sh
- apps/docs-site/scripts/verify-squash-witness.mjs
- apps/docs-site/test/witness-verification.test.mjs
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-witness-verification.md

## Verification

Use actual temporary Git repositories, source commits and the unchanged official
generator through the stable wrapper. Verify emitted bytes through the new
wrapper, assert matching receipts and no change to HEAD/index/refs/files. Test
wrong introducing revision, metadata drift, missing/corrupt/reformatted witness,
symlink and oversized output, missing source object, and hostile Git environment.
No fake shell generator or hand-written witness counts as the positive baseline.
The fixture metadata contains the producer's required identity/raw commit proof;
it is not claimed as a complete documentation snapshot. Existing full provenance
tests remain the companion consumer proof and must run unchanged.

Run the new Node test, full Portal tests/build and rendered-page assertions,
staged ownership, whitespace check and independent exact-head review. Keep
failed iterations and raw command exits; no timeout/coverage reduction.

### Executed evidence

- New stable-entrypoint integration tests passed 11/11, zero skipped, 7.102s,
  exit 0: /tmp/lmdj-witness-verification-tests-v1.log. After adding explicit
  size/mtime/ctime preservation assertions to the oversized-artifact case,
  the final version also passed through the complete Portal test population.
- After that Portal run, the argument test gained two additional refusal inputs
  (a trailing newline in Build or SHA), without implementation changes. The
  final full new suite passed 11/11, zero skipped, 5.969s, exit 0:
  /tmp/lmdj-witness-verification-tests-v2.log. The independent complete five-file
  review found no actionable finding and independently ran this final suite:
  11/11, zero skipped, 5.828s, exit 0; whitespace check also passed.
- Staged ownership passed 74/74, 6.928s, exit 0:
  /tmp/lmdj-witness-verification-scope-v1.log. Node 22 locked installation exited
  0 separately: /tmp/lmdj-witness-verification-deps-v1.log.
- Node 22 scripts/docs-site.sh check completed, exit 0: 170/170 tests, zero
  skipped (39.497s test population), production build and all 47 routes/internal
  links: /tmp/lmdj-witness-verification-docs-v1.log. The existing official
  generator, provenance library and provenance test file are byte-unchanged;
  their complete tests ran in this population, not replaced by the new fixture.
- Four assertions against actual generated operations HTML confirm the command,
  read-only existing-witness check, no regeneration/overwrite and the fresh-clone
  acceptance distinction: /tmp/lmdj-witness-verification-rendered-v1.log, exit 0.
  Tracked symlink entries were verified as actual symlinks; no checkout repair.
- The positive fixture uses a real private source object, a distinct one-parent
  squash and bytes emitted by the unchanged formal generator. A --no-local,
  single-branch clone genuinely lacks that source and remains missing it after
  verification refuses. This refusal is intentional: full fresh-clone consumer
  acceptance remains a separate required leg, not this producer-side command.
- No Product Build, durable witness execution, evidence PR, remote release,
  deployment, key or authentication configuration was changed. Pitfall
  disposition: this new recovery interface is a code-level invariant covered by
  direct tests; no new process-only recurrence. The stack remains local/unpushed.

## Version Management

Version impact: none. Recovery verification tooling only; no Product Build,
snapshot, Module, Host, Provider, Assembly or Contract identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
