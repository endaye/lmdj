# Verify snapshot-validator toolchain calls through a recording runner

## Task and declared files

- `tests/build/release_audit_workflow_test.py`
- `docs/plans/2026-09-08-lmdj-ci-audit-toolchain-behavior.md`

Baseline `75e1484f34f3d3da024a6cad12eb259056dc2de1` fails the single Node
source-string assertion after the docs-site migration changed production to
select a site root dynamically. `/tmp/lmdj-audit-toolchain-baseline.log` and
`/tmp/lmdj-ci-dependency-diagnosis.7aob2fmj/summary.json` retain the evidence.

Replace only that brittle assertion with recording-runner cases invoking
`validate_current_product_snapshot` against temporary metadata and exact
Assembly-lock bytes. Assert complete Node argv and repository cwd for current
docs-site, historical architecture-portal, and new-site precedence when both
script paths exist. Retain Python/Node workflow setup/version assertions and
all other workflow contracts. No production validator, workflow or dependency
changes; no actual audit(), release.sh, release intent, tag or network operation.
Fixture metadata intentionally remains at the historical frozen
`apps/architecture-portal/versioned_metadata/` path because production still
reads that immutable location. The test selects the active Node command root;
it does not migrate metadata or claim the Node checker itself succeeded.

## Verification

Run the focused workflow tests and related deployment workflow contracts,
staged ownership and uncached docs_static. The runner records rather than
executes commands; this proves dispatch of the validator command, not that the
Node provenance checker passed against a real Product or release.

Actual results:

- `python3 tests/build/release_audit_workflow_test.py`: 9 passed,
  `/tmp/lmdj-audit-toolchain-target.log`.
- `python3 -m unittest discover -s tests/build -p '*deploy_workflow_test.py'`:
  32 passed, `/tmp/lmdj-audit-toolchain-deploy.log`.
- `python3 tests/build/release_publish_workflow_test.py`: 7 passed,
  `/tmp/lmdj-audit-toolchain-publish.log`. These are static workflow tests,
  not publication or an actual release audit.
- After staging both files, `python3 tests/build/ci_change_scope_test.py`:
  66 passed, `/tmp/lmdj-audit-toolchain-ownership.log`.
- `scripts/local-ci.sh --base-ref origin/main --lanes docs_static --no-cache --json`:
  uncached pass, `/tmp/lmdj-audit-toolchain-docs.json`.
- `git diff --cached --check`: passed. Full CI and real release evidence are
  not claimed for this test-only Task.

## Version Management

Version impact: none — test-only behavior verification changes no Product,
Module, Contract, Assembly, snapshot or release identity.

## Documentation Impact

Documentation impact: none — no Portal page, diagram, tooling or projected
identity changes; this repairs an internal test's observation method.

## Pitfall disposition

Pitfall impact: none — the stale string assertion is derivable from the test
and dynamic source. Exact recorded argv/cwd avoids another implementation-text
assumption. The release skill was inspected only to confirm boundaries; no
release audit or operation is part of this Task.
