# Candidate cut and squash source proof

Delivery base: 26ff32bb21b2d881aca5acca3fa2e8c25f541a22.
Original Task: 6ce1fab882e98f57d69557432e38d9379a4ff0fd (base
c259fd12f7fbb1edae4f364f361f75e14a4f922a). Keep original-stack results below
as historical evidence, not validation of the new delivery base.

## Task and files

Add the source verifier needed by the future candidate PR adapter. Consume
the concrete cut workspace and its private source/snapshot/cut bindings;
reconstruct the cut from committed source plus snapshot bytes. Before squash,
require the original frozen input projection to remain unchanged on main.
After squash, verify that projection on the actual single parent and prove the
exact candidate patch applied to that parent yields the actual squash tree.
Subsequent main advancement must not silently change the fixed target.

Declared files:

- tools/release/candidate_source.py
- tests/build/release_candidate_source_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-squash-proof.md

Only passive Git proof and private temporary indexes; no checkout/ref/fetch or
remote writes. This does not establish Task test completion, protected-main
authority, review eligibility, witness acceptance or release CI. In particular,
cut-binding is an intent, not a substitute for the trusted parent's Task proof.
The caller must authenticate live main and the original request/frozen inputs.
BUILD high-watermark/all-history allocation competition remains owned by the
reservation gate; equal endpoint projection is not that allocation proof.

## Verification

Six actual Git cases: preserve docs advancement and fixed candidate despite later
main changes; refuse lost parent docs, pre-squash product drift, rebound cut,
unreachable squash and a two-parent merge. Assert no HEAD/index/ref/worktree
mutation in the successful journey. Register projection and binding groups at
the existing 30-second contract budget. Run ownership and current Portal.

The inherited cut fixture now seeds each serial class through real material,
source installation and a Bash snapshot subprocess, restoring the full emitted
container at its original paths for each case. Every source-proof case still
executes its own cut preparation and actual Git object/parent proof; source
generation is not repeated per case. The Bash snapshot and callback checks are
fixtures, not full Portal or trusted Task-verifier composition. The prior
explicit full Portal journey is separate companion evidence, not a run of this
new consumer. Keep both three-case registrations at 30 seconds each.

### Delivery verification

- Direct six-case suite passed, exit 0, 41.810 seconds:
  /tmp/lmdj-candidate-squash-delivery-tests-v1.log.
- Configured CTest passed 2/2, exit 0, 40.06 seconds:
  /tmp/lmdj-candidate-squash-delivery-ctest-v1.log. Actual child populations
  were projection 3/3 (22.820s), binding 3/3 (16.801s), no skipped tests or
  widened timeouts. The new consumer executes against actual cut receipts.
- Staged ownership passed 74/74, exit 0, 5.882 seconds:
  /tmp/lmdj-candidate-squash-delivery-scope-v1.log. Development configuration
  selected Python 3.14.7 and completed successfully; its log is
  /tmp/lmdj-candidate-squash-delivery-configure-v1.log.
- Independent review inspected all five files, actual source/snapshot binding,
  exact-parent reconstruction and inherited seed compatibility; no actionable
  findings. After its static review, the independent reviewer ran
  SourceProjectionTest.test_original_cut_and_squash_with_docs_advance_preserve_actual_parent:
  1/1, exit 0, 14.348 seconds under Python 3.11.15. This was one independent
  case, not the whole suite or the registered Python 3.14 CTest run.
- A separate consumer diagnostic passed with exit 0 using the retained real
  Portal run at /tmp/lmdj-candidate-portal-delivery.4trE0h/run-v1. It consumed
  the actual source, snapshot and cut receipts, proving cut
  dcc6e0b1722fda387eb177b96fd4dacab03846e6 and fixture squash
  e1bf382fa1e71e3b85d40443eb49c6c98178fb3b on original parent
  df4e49be9ce7168f7ae25f1e0f1f35fb4b75f032. HEAD, raw index, refs, checkout
  status and all four original journal files were byte-for-byte unchanged.
  Script and output: /tmp/lmdj-candidate-squash-delivery-retained-proof-v1.py
  and /tmp/lmdj-candidate-squash-delivery-retained-proof-v1.log. The diagnostic
  records the new consumer digest; it recomputes the deterministic frozen input
  from the unchanged original base, not a nonexistent persisted frozen-dict
  transcript. It is not a rerun of Portal, witness generation, remote merge or
  authenticated service intake, and does not replace the permanent regressions.
- Node 22 scripts/docs-site.sh check passed, exit 0, with 159/159 tests,
  zero skipped and 47 routes/internal links:
  /tmp/lmdj-candidate-squash-delivery-docs-v1.log. Four assertions against the
  generated operations HTML passed (exit 0) and confirm the source-proof and
  remaining-gate boundaries: /tmp/lmdj-candidate-squash-delivery-rendered-v1.log.
  This current Portal build allocates no Product Build or immutable snapshot.
- Pitfall disposition remains code-regression coverage: exact-parent and tree
  checks are directly expressible, while existing witness and complete-journey
  obligations stay open at their owning parent transitions.

### Historical original-stack verification

Observed verification: direct 6/6 passed in 33.741 seconds. Formal CTest 2/2
passed (projection 20.92 seconds; binding 16.39 seconds), preserving both
30-second limits. Staged ownership 74/74 passed in 5.614 seconds. Independent
read-only review clean, with the allocation-proof limitation made explicit.
Logs: /tmp/lmdj-candidate-source-proof-tests.log,
/tmp/lmdj-candidate-source-proof-ctest.log,
/tmp/lmdj-candidate-source-proof-ownership.log. Portal verification passed all
152 tests (zero skipped) and 47 routes; retained in
/tmp/lmdj-candidate-source-proof-portal.log. The new source-proof paragraph was
also checked in the actual built operations/version-and-release HTML.

Pitfall disposition: source-tree equality and ancestry rules are fully expressed
by code regressions; no new process invariant or pitfall entry.

## Version Management

Version impact: none. Internal source-verification adapter only.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
