# Durable candidate snapshot command execution

Delivery base: faf70d4d4f7e463764e9fc05633739634d043cd0.
Original Task: af04ba5237ee34c9b5a00f786fb2e04dc76f7975 (base
f74ece1fc5decc97a837c1891d6e89ab507bce65). Original-stack verification below
is historical evidence, not a claim about this delivery base.
Integrate the canonical storage correction from
c259fd12f7fbb1edae4f364f361f75e14a4f922a for this command runner and fixtures.

## Task and files

Connect the actual installed source receipt to official version/resume-version
commands, using the same source workspace writer lock. Persist enrollment and
command intent before execution. Generation runs at most once; later calls only
verify the original snapshot, retaining failed or unknown generation results.
Missing enrolled state refuses re-generation. Bound resume attempts to at most
three and keep the original 900-second Portal command budget.

Declared files:

- tools/release/candidate_snapshot.py
- tools/release/task_verification.py
- tests/build/release_candidate_snapshot_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-snapshot-run.md

Require the concrete source installer, exact persisted source binding, original
request digest, branch/HEAD/tree/index, visible index and unchanged tracked
command source. Authenticate original authority before and after each child.
Compare raw tracked file modes and bytes to Git object identities, not filtered
Git diff output. Reuse that exact comparison in the original Task verifier with
no exclusions; candidate resume allows only the versions inventory to change.
Reuse the executed Task command runner with scrubbed environment and inherited
writer descriptor; a child result records actual exit/output digest/byte length.
The verified status requires a successful concrete resume-version command, not
merely a saved success marker. Each later call reruns that verifier within the
remaining budget.
After the first successful resume, bind every generated file's path, byte length
and SHA-256. Reject later drift before another command and after the check.
The source/snapshot identity digest stays stable across verification retries;
the separate append-only command-history digest records each actual attempt.
Bound encoded receipt size before writing so a newly saved state remains
readable under the same limit. Sanitize every authorization callback exception
at its own boundary, independently of the exception's nominal type.

## Verification

Actual temporary Git reservation/material/source installation and actual Bash
children exercise successful generation/resume, child failure with retained
exit, real controller death after generation, missing output, missing state,
tracked-command drift, exhausted budget and failed authorization. The fixture
command replaces Portal generation/checks; companion Node snapshot tests own
actual content/provenance semantics. These command fixtures alone do not prove
an end-to-end official snapshot generation or a released candidate.

Run both registered recovery/safety suites, original source workspace suites,
staged ownership, and full Portal check. No timeout or coverage floor changes.
Original authority/control/toolchain authentication is still a required trusted
callback; production intake/configuration is not implemented by this Task.
Final cut commit/review/squash/witness, exact-target CI and the full service
composition remain open. No real Build allocation, signing, remote write,
deployment or Channel promotion occurs in this development Task.

### Historical original-stack evidence

- Initial command fixtures passed 8/8, then byte-binding coverage passed 9/9;
  logs: /tmp/lmdj-candidate-snapshot-tests-v1.log and -tests-v2.log.
- Independent review found a real clean-filter bypass: a locally replaced
  command could appear Git-clean and execute. Fixed by sharing raw blob/mode
  checks with the existing Task verifier and removing filtered diff/status from
  the candidate's source and snapshot inventory checks. The causal regression
  establishes empty Git diff before asserting refusal and no malicious child.
  Log: /tmp/lmdj-candidate-snapshot-filter.log, exit 0.
- Five registered suites passed after that repair: candidate recovery/safety,
  both original source workspace suites (15 cases), original Task verifier
  (15 cases); /tmp/lmdj-candidate-snapshot-ctest-v2.log, exit 0, 85.91 seconds.
- After authorization cleaning, both candidate suites passed again, 13 cases;
  /tmp/lmdj-candidate-snapshot-ctest-v3.log, exit 0, 41.73 seconds. The added
  receipt-size test passed independently before final registration.
- Final two candidate registrations passed with all 14 cases, exit 0;
  /tmp/lmdj-candidate-snapshot-ctest-v4.log. Final staged ownership passed
  74/74, exit 0; /tmp/lmdj-candidate-snapshot-scope-v3.log.
- Final independent review is clean. The reviewer independently ran four
  focused real-workspace cases after the filter repair and inspected the later
  callback sanitation and receipt-bound fixes without concurrent full-suite
  execution. Earlier actionable findings remain recorded above.
- Independent review also found that callback exceptions could masquerade as
  sanitized internal exceptions. Both PermissionError and JournalError secret
  fixtures now refuse without exposing original text or starting commands;
  /tmp/lmdj-candidate-snapshot-authority-v2.log, 2/2, exit 0. Earlier iterations
  remain retained, including review findings; no backend approval was invented.
- Node 22 scripts/docs-site.sh check passed: 151 tests, production build and
  47 routes/internal links; /tmp/lmdj-candidate-snapshot-portal.log, exit 0.
  Inspected the actual generated operations page for the new command-runner
  paragraph, rather than treating the build exit alone as the page evidence.
- Pitfall disposition: the source identity and callback-boundary defects are
  fully captured by direct regression tests. Search found no matching open
  filter entry; no new process-only ledger entry. Complete official generator
  integration and production authority/toolchain/config authentication remain
  unexercised; neither shell fixtures nor a current Portal build discharge them.

### Delivery-base verification and limits

- Preserved current `PublicationTaskVerifier` enrollment marker, missing-state
  refusal, bounded writer, authorization sanitation and isolated whitespace
  Git execution. Only its existing raw blob/mode loop is shared; its original
  call has no mutable-path exclusions. The candidate's sole mutable tracked
  path is canonical `apps/architecture-portal/versions.json`, never the alias.
- Current-layout regression, before the canonical correction: actual source
  installation and Bash generation reached the post-child raw check, then
  failed on the canonical versions bytes (1 error, 8.775s, exit 1).
  Log: `/tmp/lmdj-candidate-snapshot-delivery-alias-red-v1.log`.
  The source rejection was a wrong mutable-path allowance, not authorization
  failure and not a failure of the official Portal generator (fixture Bash).
- Fixtures now retain the actual compatibility alias and canonical paths;
  source worktrees use command-local `core.symlinks=true`. The clean-filter
  regression establishes an empty ordinary Git diff through the actual local
  filter and a nonempty diff through the trusted filter-disabled helper, then
  requires the runner's raw-byte refusal and no malicious command execution.
- Existing source-workspace registrations remain recovery 4, crash 2 and
  safety 9. This Task adds snapshot recovery 4 and snapshot safety/state 10;
  each retains its original 30-second budget, with no omitted test case.
- A future cut consumer must authenticate a completed verification boundary:
  a saved old snapshot and a latest command exit 0 alone cannot prove that the
  latest post-child authorization passed. This runner returns no success when
  that check fails. The consumer and full Portal candidate journey are still
  required subsequent work, not discharged by command fixtures.
- Initial direct execution passed 14/14 in 88.006s, exit 0;
  `/tmp/lmdj-candidate-snapshot-delivery-tests-v1.log`. First CTest returned
  exit 8 in 151.41s: snapshot recovery passed (28.88s), safety timed out at
  30.03s, original source groups passed (27.13/15.80/21.25s), and unchanged
  Task verification passed (28.30s). Preserve both
  `/tmp/lmdj-candidate-snapshot-delivery-ctest-v1.log` and
  `/tmp/lmdj-candidate-snapshot-delivery-ctest-child-v1.log`; no full safety
  pass is inferred from the timed-out child.
- Profiling v1 was an invalid invocation: wrapper exit 0 concealed unittest
  `_FailedTest`, with no actual safety case. It remains recorded at
  `/tmp/lmdj-candidate-snapshot-delivery-profile-v1.log`. Corrected v2 directly
  constructs the real suite and propagates `result.wasSuccessful()` to exit:
  1/1, 7.142s, exit 0, setup 5.579s and source installation 4.661s;
  `/tmp/lmdj-candidate-snapshot-delivery-profile-v2.log`.
- Fixture optimization only: include fixed files in the actual initial commit
  before freeze. Safety creates one real installed-source seed per serial
  class, then restores independent complete copies to the same test-created
  temporary paths. Each case uses fresh Material/Workspace/Runner objects,
  authorization list and deep-copied actual emitted request/source receipts;
  no Git pointer, raw identity or binding is synthesized or rewritten.
  Copies preserve symlinks/modes. Writer release is checked before the seed
  backup and after each case; cleanup stacks are not shared between cases.
  Recovery still generates from scratch for each of its four scenarios and
  the original 15 source cases are unchanged. Safety no longer claims to
  regenerate the source for each case. No production check, fsync, lock,
  authorization, CTest registration, timeout or budget was reduced or enlarged.
- AST inventory confirms the original 14 names: recovery 4, safety 9, state 1;
  `/tmp/lmdj-candidate-snapshot-delivery-inventory-v1.log`, exit 0. This
  inventory is not execution evidence; final registered and reverse-order
  execution results are recorded below.
- Final unchanged CTest selection
  `^build\.release_(candidate_snapshot_recovery|candidate_snapshot_safety|candidate_workspace_recovery|candidate_workspace_crash|candidate_workspace_safety|task_verification)$`
  passed 6/6 in 135.80s, exit 0:
  `/tmp/lmdj-candidate-snapshot-delivery-ctest-v2.log`.
  Actual child counts/durations: snapshot recovery 4/27.108s, snapshot
  safety/state 10/16.874s, source recovery 4/26.695s, source crash 2/15.067s,
  source safety 9/21.042s, original Task verification 25/28.260s. All passed,
  none skipped; full child output is in this worktree's
  `build/core/dev/Testing/Temporary/LastTest.log`.
- Safety reverse order, using the configured Python 3.14 interpreter, passed
  all 9 cases in 16.187s, exit 0:
  `/tmp/lmdj-candidate-snapshot-delivery-reverse-v1.log`.
  The runner propagates child test success/failure; it does not use profiler
  wrapper status. Full Portal execution starts only after these runs complete.
- Independent review inspected the complete six-file Task and the later
  fixture changes without new findings; it independently ran the actual
  clean-filter refusal before fixture optimization (1/1, 8.534s, exit 0).
  The later fixture optimization was independently re-reviewed as well;
  the original clean-filter independent run is not represented as a rerun of
  the optimized fixture.
- Final staged ownership/admission: 74/74, 5.741s, exit 0;
  `/tmp/lmdj-candidate-snapshot-delivery-scope-v2.log`. Initial staged run
  (74/74, 5.959s) remains in `-scope-v1.log`. Diff check passed for all six
  declared files. AST comparison independently confirms all original
  PublicationTaskVerifier methods except the extracted `_checkout` are
  unchanged: `/tmp/lmdj-candidate-snapshot-delivery-verifier-preservation-v1.log`.
- Locked Node 22 dependencies and `scripts/docs-site.sh check` passed, exit 0:
  159/159 tests, zero skipped, production build and 47 routes/internal links.
  Logs: `/tmp/lmdj-candidate-snapshot-delivery-deps-v1.log` and
  `/tmp/lmdj-candidate-snapshot-delivery-docs-v1.log`. Actual generated
  operations HTML contains the command runner, canonical mutable-path rule,
  fresh verification and incomplete-cut/service boundaries; explicit output
  check exit 0: `/tmp/lmdj-candidate-snapshot-delivery-rendered-v1.log`.
  This current Portal build does not perform a candidate snapshot freeze.
- Pitfall disposition: canonical-path and filter behavior have direct
  regressions; the fixture performance change preserves every registered case
  and production boundary. No new process-only ledger mechanism is claimed.
  No host, signing, remote, Product allocation or publication operation is
  performed by this Task.

## Version Management

Version impact: none

Reason: local controller implementation; generated fixture candidates are not
real Product Builds or team-testing allocations.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/
