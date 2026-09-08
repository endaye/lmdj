# Restore the migrated pitfall exit reference

## Task and declared files

- `.agents/pitfalls/portal-impact-two-dot-base-diff.md`
- `docs/plans/2026-09-08-lmdj-ci-pitfall-docs-site-path.md`

The docs-site migration moved the enforcing test to
`apps/docs-site/test/changed-files.test.mjs` but left the machine-readable
pitfall `exit` at the removed path. The baseline ledger suite reports exactly
that missing exit. Change this active reference and the same entry's two live
How-to-apply source/test pointers; preserve the original recurrences, absorbed
status and historical explanation.

The destination still tests the real merge-base behavior: a behind-base branch
excludes other PR changes; truthful none remains valid; genuine page edits are
not excused; added-file scope does not inherit a base deletion; the checker
uses both exact revisions; malformed revisions are rejected. No gate logic or
test selection changes.

## Verification

Baseline `python3 tests/build/ci_pitfall_ledger_test.py`: 14 tests, one expected
missing-exit failure, retained in `/tmp/lmdj-pitfall-docs-site-baseline.log`.
Verify the repaired ledger suite, the six destination Node tests, staged
ownership and uncached docs_static before committing. This is not a full
Portal build, product test, release audit or remote acceptance claim.

Actual results: ledger 14 passed (`/tmp/lmdj-pitfall-docs-site-target.log`);
`node --test apps/docs-site/test/changed-files.test.mjs` 6 passed, zero skips
(`/tmp/lmdj-pitfall-docs-site-node.log`); after staging both declared files,
`python3 tests/build/ci_change_scope_test.py` 66 passed
(`/tmp/lmdj-pitfall-docs-site-ownership.log`).
`scripts/local-ci.sh --base-ref origin/main --lanes docs_static --no-cache --json`
passed without cache (`/tmp/lmdj-pitfall-docs-site-docs.json`).
`git diff --cached --check` passed. Root independently repeated ledger 14 and
destination Node 6 successfully. Full CI is not claimed or required for this
pointer-only change.

## Version Management

Version impact: none — repair of an internal governance reference changes no
product, contract, build or release identity.

## Documentation Impact

Documentation impact: none — no Portal page, diagram, tooling or projected
source fact changes; only the existing ledger's executable exit pointer moves.

## Pitfall disposition

Repair the existing entry's exit path without adding a recurrence of the
original two-dot defect: that defect did not recur and the enforcing behavior
still exists. The existing ledger validator caught the dangling reference.
