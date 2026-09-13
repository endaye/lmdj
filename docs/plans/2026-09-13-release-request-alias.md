# Persist duplicate request identity across completion

Delivery base: `d1f95844075b5d7f74054ee562b5f50708173738`.
Reapply Task `3a0ec76c6bc1f7d193c30c6da4071df10dc9a85e`, preserving the
newer bounded journal writes and parent before-write guards. Duplicate admission
must remain idempotent after the original release completes. Store a private,
canonical, immutable alias before advancing
the original request, after both authorities have been authenticated.

Declared files:

- tools/release/orchestration.py
- tools/release/orchestration_driver.py
- tests/build/release_orchestration_driver_test.py
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-request-alias.md

Alias records bind the complete incoming request to the original request ID
and digest, never to a mutable completion flag. Resolution revalidates the
original record and both authorities. No alias chains, same-ID scope edits or
alias-to-new-request conversion. Use existing writer ownership/flock and
atomic fsync storage semantics. This is one private journal directory, not
global service authentication or cross-directory deduplication.

## Verification

Actual driver/private journal/far-side fixtures: reproduce replay-after-complete
creating a second release; verify durable replay and resume through alias;
reject changed alias scope, revoked original authority, corrupt/dangling aliases
and alias reuse by create; crash after alias save recovers the original operation.
Run driver/journal/managed adapter suites, ownership, Portal and independent
review. No actual CI/release/deployment/signing or service acceptance.

## Version Management

Version impact: none

Reason: release control-plane persistence only, no Product/Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

## Evidence

Original-stack results are historical, not current-head acceptance. Current
delivery uses the declared base above and retains both causal failures:

- Actual driver replay after completing the original release incorrectly created
  a second release: 1 failure, 0.101s, exit 1, retained in
  `/tmp/lmdj-request-alias-delivery-red-v1.log`.
- Extracting the atomic writer exposed an alias path that bypassed the inherited
  1MiB write limit. The regression uses the real unchanged limit, a format-valid
  request whose actual journal bytes are limit minus 100, and captures the
  oversized alias bytes passed to the actual writer. The strengthened red has
  1 failure, 0.086s, exit 1, retained in
  `/tmp/lmdj-request-alias-delivery-size-red-v2.log`; the earlier failure remains
  in `size-red-v1.log` under the same prefix. This synthetic repository string is
  a journal-format fixture, not evidence of production repository authorization.
  Moving the existing guard into `_write` covers both original and alias records
  before temporary-file creation. The green asserts unchanged original bytes,
  absent alias and no temporary inventory, without reducing the limit.

Current verification (all exit 0 unless otherwise noted):

- Direct driver: 32/32, 0.671s; journal: 21/21, 0.151s. Logs:
  `/tmp/lmdj-request-alias-delivery-driver-v2.log` and
  `/tmp/lmdj-request-alias-delivery-journal-v2.log`.
- Registered CTest: 4/4, 13.51s; actual child populations journal 21, driver 32,
  managed dispatch 20, managed PR transition 26, all passed without skips.
  Selection: `^build\.release_(orchestration|orchestration_driver|managed_dispatch|managed_pr_transition)$`.
  Log: `/tmp/lmdj-request-alias-delivery-ctest-v1.log`; child evidence:
  `build/core/dev/Testing/Temporary/LastTest.log` in this worktree.
- Independent reviewer `/root/release_journal_review` inspected all five files,
  including the plan, and found no actionable finding. Independently executed
  driver 32/32 (0.674s), journal 21/21 (0.184s) and diff check, all exit 0.
  This local review is not owner adoption or live PR merge eligibility.
- Locked Portal dependencies installed with Node 22; no lockfile changes or
  automatic dependency repairs. `scripts/docs-site.sh check` passed: 144/144
  tests, 47 pages and built routes, 10 diagram sources / 20 outputs, no skipped
  tests. Log: `/tmp/lmdj-request-alias-delivery-docs-v1.log`.
- After staging exactly the five declared files, ownership/admission suite
  `python3 tests/build/ci_change_scope_test.py` passed 74/74 in 14.266s.
  Log: `/tmp/lmdj-request-alias-delivery-scope-v1.log`. Staged diff check passed;
  no thresholds, timeouts or lane selection were weakened.

Pitfall disposition: direct replay/persistence invariant, no new process-only
ledger entry. Production intake/service, cross-directory deduplication and
full release acceptance remain incomplete.
