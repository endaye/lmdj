# Candidate branch transport

Delivery base: 9021b0c0d428858c2d891dbb760eb72c6e2a9b87.
Original Task: 5d87afa5033451c111918e8789bcf1b9f4c92e14. Original-stack
results below are historical, not verification of this delivery. Preserve the
current enrollment marker, bounded state and early document preflight.

## Task and files

Reuse the exact create-only Git branch transport for the closed candidate spec
already used by CandidatePullRequest. Keep the publication defaults unchanged.
The only advertised ref is the operation-bound feat/release-candidate branch,
pointing at the complete cut SHA rather than its private source SHA.

Declared files:

- tools/release/evidence_branch.py
- tools/release/candidate_branch.py
- tests/build/release_candidate_branch_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-branch.md

No overwrite, broad push, source-retention-ref push or tag push. Keep the same
isolated Git configuration, canonical HTTPS remote, credential handling,
inherited writer lock, atomic expected-absent lease, persisted claim and exact
post-push observations. Unknown effects reconcile rather than resend; an adopted
ref is not recreated after deletion. A trusted production authorize gate must
still verify original request, completed Task/source evidence, allocation
competition and live protected-main configuration.

## Verification

Run the unchanged publication branch suite and full inherited real-Git candidate
suite against temporary bare remotes. Preserve lost-ACK, competing creation,
no-effect unknown, state drift/corruption, real process death on both sides of
the push and orphaned Git child lock tests. Candidate-specific cases reject
cross-scope specs and private-source-as-cut before transport. Fixture identity
and authorization callbacks are not real main/review/Task proof. Only fixture
transport enables local file URLs; production has no remote override.

Register contract/30-second test, run staged ownership and Portal check with
built HTML inspection and independent review. Parent durable initialization,
branch-to-PR/witness composition and service command wiring remain unfinished;
this transport alone must not report an entire candidate step complete.

### Delivery verification

- A thin original port reproduced the current-base mismatch: the new candidate
  scope hit the publication-only document preflight, one error, exit 1,
  0.195 seconds. Retained evidence:
  /tmp/lmdj-candidate-branch-delivery-preflight-red-v1.log.
  Route that existing early preflight through the fixed document hook; do not
  remove it or defer it until after durable enrollment.
- Direct candidate 23/23 passed (15.462s), publication 21/21 passed (15.054s),
  both exit 0. The candidate inherits all current publication lifecycle cases,
  overrides the state-size fixture with its product_build field and keeps the
  same no-replacement assertions. Added oversized-document rejection verifies
  no journal, authorization callback, push or remote ref. Cross-scope/private
  source rejection and real before/after-effect controller death remain covered.
  Logs: /tmp/lmdj-candidate-branch-delivery-tests-v1.log and
  /tmp/lmdj-candidate-branch-delivery-publication-v1.log.
- Registered CTest passed 3/3, exit 0, 32.32 seconds: candidate branch 23/23
  (16.631s), publication branch 21/21 (15.055s), candidate PR 39/39 (0.104s).
  No cases skipped and no timeout changed: candidate branch/PR retain 30 seconds,
  the current-base publication branch retains 60 seconds. Evidence:
  /tmp/lmdj-candidate-branch-delivery-ctest-v1.log. Development configuration
  exited 0 separately in /tmp/lmdj-candidate-branch-delivery-configure-v1.log.
- AST comparison confirms all seven existing shared branch methods are identical
  after normalizing only the fixed spec/document hooks; the original publication
  test file is byte-unchanged. This source comparison supplements execution:
  /tmp/lmdj-candidate-branch-delivery-preservation-v1.log, exit 0.
- Staged ownership passed 74/74, 5.663s, exit 0:
  /tmp/lmdj-candidate-branch-delivery-scope-v1.log.
- Initial dependency invocation incorrectly used the snapshot directory
  apps/architecture-portal, which has no package lock; npm refused, exit 1,
  /tmp/lmdj-candidate-branch-delivery-deps-v1.log. No lock was generated or changed.
  The actual stable scripts/docs-site.sh install entrypoint targets apps/docs-site;
  it completed with Node 22, exit 0, in the separate deps-v2.log under that prefix.
- Independent six-file review found no actionable finding; independently ran
  oversized-document and real before/after-effect death regressions, 2/2,
  1.620 seconds, exit 0. No real GitHub, provider, host or credential access.
- Node 22 scripts/docs-site.sh check completed, exit 0: 159/159 tests, zero
  skipped, production build and 47 routes/internal links. Evidence:
  /tmp/lmdj-candidate-branch-delivery-docs-v1.log. Four assertions against actual
  generated HTML confirm create-only transport, private-ref exclusion, missing
  enrollment refusal and the incomplete-candidate boundary:
  /tmp/lmdj-candidate-branch-delivery-rendered-v1.log, exit 0.
  All tracked symlink entries were checked as actual symlinks; no checkout or
  shared Git configuration repair was needed. No Product Build was allocated.
- Pitfall disposition: scope/preflight mismatch is a code invariant covered by
  the exact-create and document-bound tests; no new process-only ledger entry.
  Parent enrollment/guard composition, branch-to-PR/witness sequencing, trusted
  production gates and public service commands remain outside this Task.
  This dependent stack remains local; no remote push, PR or release was issued.

### Historical original-stack verification

Observed: direct candidate 14/14 passed (8.304 seconds), unchanged publication
13/13 passed (7.609 seconds). Registered CTest 2/2 passed: candidate 8.64 seconds,
publication 8.16 seconds; both retain TIMEOUT 30. Independent six-file read-only
review clean. Logs: /tmp/lmdj-candidate-branch-tests.log,
/tmp/lmdj-candidate-branch-publication-tests.log,
/tmp/lmdj-candidate-branch-ctest.log. Staged ownership passed 74/74 in 5.771
seconds (/tmp/lmdj-candidate-branch-ownership.log). Portal passed all 152 tests,
zero skipped, and 47 routes in /tmp/lmdj-candidate-branch-portal.log; the new
paragraph was checked in the actual built version-and-release HTML.

Fresh upstream #1266 remains OPEN/UNSTABLE at
c8fab3b67b6abe3bff708b5563acfc84b0e9e671; paginated comments contain no owner
review attestation. The stack stays local/unpushed, not merged or activated.

Pitfall disposition: the adapter's rules are code-level invariants already
covered by the retained fault tests; no new process-ledger entry.

## Version Management

Version impact: none. Internal transport with fixture-only identities.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
