# Repair current canary identity inputs

Status: implemented and locally verified; remote shipping evidence belongs to
the Task PR. Relates to #1029 and #749.

## Task and declared files

One repair unit restores the Runtime identity projections of the existing
declared manifests and makes preparation tests independent of historical Host
versions. The production metadata verifier correctly rejects stale inputs; do
not relax it or change the proposal inventory.

Declared files:

- this plan;
- `products/lmdj/generated/web-runtime-identity.json`;
- `products/lmdj/generated/web-runtime-identity.mjs`;
- `tests/build/version_test.py`;
- `tests/build/ci_canary_preparation_test.py`;
- `apps/docs-site/docs/assembly/lmdj.mdx`;
- `.agents/pitfalls/generated-identity-check-skips-real-tree.md`.

Add the actual-repository `write_or_check(repo_root, check=True)` call to the
existing version test, beside (not instead of) synthetic generator coverage.
The settled invariant is byte equality between both committed projections and
canonical generation from active manifests. This is deterministic and catches
stale Product, Assembly, Platform or Host identity, with the existing generator's
why/remedy diagnostic. It adds no PR required check or new workflow.

Preparation tests derive their independent expected patch/minor/pre-bump cases
from the pinned input manifests, not from the production preparation output.
Keep real Git inputs coherent and retain every refusal and replay assertion.
Canonical metadata and full handoff tests continue to copy actual identities;
they must not be normalized to an obsolete synthetic production version.

## Verification and acceptance

1. Reproduce the current Runtime identity failure; prove the newly wired real-
   tree test fails before regeneration. Then generate the existing JSON/MJS
   pair with `python3 tools/web-runtime/generate_runtime_identity.py --repo-root .`
   and verify `--check` plus `python3 tests/build/version_test.py`.
2. Run `python3 -m unittest discover -s tests/build -p 'ci_canary_*test.py'`:
   patch/minor, sufficient/insufficient/backwards/major pre-bumps, occupied
   changelog, stale/forged input, canonical generation and full persisted
   producer-to-metadata/replay journeys retain their existing assertions.
3. Run complete `ci_*_test.py` discovery, staged and committed ownership,
   `scripts/architecture-portal.sh check`, final range and PR declarations.
   Do not narrow discovery, raise timeouts, skip a test or weaken guards.
4. Ship through current-head review and expected-head squash; verify actual
   merged file inventory and bytes. Local fixture success does not establish
   live canary executor, deployment isolation or delivery activation.

## Version Management

Version impact: none. Regenerate stale projections of already declared Product,
Platform and Host identities; no manifest bump, new Product allocation, Assembly
change, immutable snapshot rewrite, tag, release, deployment or promotion.

## Documentation Impact

Documentation impact: required
Affected portal pages: /assembly/lmdj
Reason: distinguish manifest-derived current identity from historical allocation
notes, and document the real-tree projection check. No architecture boundary or
source diagram changes; existing immutable snapshots remain untouched.

## Pitfall disposition

This is a recurrence of `generated-identity-check-skips-real-tree` (#749,
then #1029). Absorb it into `gate:tests/build/version_test.py` once the real-tree
red-to-green check and both projection rejection fixtures are verified.

## Local evidence

On base `90de75e668988fcf203274eea737c87f0d6d3d5c`, the added real-tree call
failed with expected Product Build `1.0.45.0` versus generated `1.0.44.0`, naming
the source, consumer and generator remedy. Canonical regeneration then passed
`--check` and the complete version test, including unchanged JSON/MJS negative
fixtures. Only derived Product/Assembly/Platform/Host identity fields changed.

All 210 canary tests pass; all 2,075 CI-contract tests pass with the existing
one optional actionlint semantic check skipped (tool unavailable). Portal
verification passes 112 tests and the production build's 44 route/link checks.
These are local results, not a complete native/Web product proof, live canary
execution, remote report receipt or deployment acceptance. The pre-existing
docs dependency audit reports 27 advisories; dependency repair is outside this
identity-input Task. No test or required scope was removed.
