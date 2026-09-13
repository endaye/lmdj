# Executed witness Task checks

Delivery base: 634ffc7878c3e6ef84332903cadd9af84d191e74.

## Task

Implement the missing actual Task-command leg of the independent witness PR.
The concrete runner consumes CandidateWitnessTask's staged and committed
boundaries under its original source-then-Task writers. Execute the three
existing Task commands in each phase: full Portal check, ownership/admission,
and whitespace against the original base (never an empty postcommit diff).
Bind exact Task identity, original witness receipt, control revision and trusted
toolchain PATH to an owner-only command journal. Persist each intent before
execution and actual exit/output digest/length before confirmation. Revalidate
original authority, retained bindings and exact checkout before and after each
command. Only six confirmed successful commands produce PR-bound evidence.

Cold resume reuses confirmed commands and continues only an unstarted command;
failed/started/unconfirmed outcomes never replay. Missing enrolled state cannot
restart the budget. A retained committed Task without staged evidence cannot
retroactively claim staged checks. A passive reader validates the exact
witness spec and evidence digest, not a caller-supplied passing summary.

Add a guarded callback form to CandidateWitnessTask without changing existing
trusted fixture callbacks. Reuse the existing bounded-memory process executor;
inherit both real writer lock descriptors so a surviving child fences source
and Task after controller death. No new credential or command environment
inheritance, no timeout increase, and no production retries.

## Declared files

- tools/release/witness_checks.py
- tools/release/candidate_witness_task.py
- tools/release/task_verification.py
- tests/build/release_witness_checks_test.py
- tests/build/release_task_verification_test.py
- tests/build/release_candidate_portal_journey.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-14-release-witness-checks.md

## Verification

Lowest tier: contract, with actual Git, actual subprocess output and actual
controller death/lock inheritance. The narrow fixture uses the official witness
producer and real Task, but labelled small Portal/ownership entrypoints; it is
not full Portal-content acceptance. Cover each phase, cold read/prepare, failed
and unknown command refusal, missing/corrupt/rebound state, lost final authority,
checkout drift and both-writer fencing. New command groups start with explicit
120-second budgets; keep every existing command and group budget unchanged.
Run existing Task and process-executor regressions. Run locked Portal install,
full Portal check and rendered-page assertions for the current documentation.
Retain a separate real full-Portal producer/Task rehearsal using the new runner;
replace the existing rehearsal's hand-driven witness check callback with the
concrete runner, assert six persisted actual command results and no cold replay,
then retain its actual far-side squash and source-absent Portal assertions.
Do not substitute narrow fixture success for that acceptance leg.
Stage only declared files, run ownership/admission, inspect the complete diff,
and obtain independent complete-diff and exact-head review before local handoff.

The inherited dependent-stack hold remains: local/unpushed pending upstream
PR #1296 owner adoption. No GitHub business write, release/signing/deployment,
host/auth/key/protection change, cleanup, or invented owner attestation.
This Task does not implement the production request service, review/protection
factories, complete CI, signing or final release acceptance. Those remain in the
full single-command-release objective, not redefined as this local Task.

## Version Management

Version impact: none

Reason: release command evidence only; no product or public Contract identity,
Product Build, Assembly, snapshot, tag or release is allocated or modified.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: describe executed witness Task evidence and its remaining production
composition and release-acceptance boundaries.

## Execution evidence

Verification ran on the nine declared local, uncommitted files. Non-plan tested
bytes are bound by `/tmp/lmdj-witness-checks-tested-files-v3.sha256`; no production
or test changes followed that manifest. Commit verification must preserve those
exact bytes. These are local development artifacts,
not owner adoption, remote review, release or deployment acceptance.

- Actual process-executor regressions: 26 tests passed, exit 0, including both
  writer locks held by an orphan child. Raw log:
  `/tmp/lmdj-witness-checks-executor-v2.log`.
- Locked Node 22 installation and current Portal check passed: 170 tests,
  zero failures/skips, 47 routes and internal links validated. Four actual
  rendered-page assertions also passed. Logs:
  `/tmp/lmdj-witness-checks-install-v1.log`,
  `/tmp/lmdj-witness-checks-docs-v1.log`, and
  `/tmp/lmdj-witness-checks-rendered-v2.log`.
- Final configured CTest batch executed 19 groups, exit 8: 17 groups passed,
  including all 12 new individual witness-check cases. Existing Task lifecycle
  timed out at 120.04 seconds; existing Task authority failed in class setup
  before any case ran. Neither is classified as passing or waived. Complete
  child output is retained in
  `/tmp/lmdj-witness-checks-ctest-v1-LastTest.log`, with the two failed groups
  in `/tmp/lmdj-witness-checks-ctest-v1-LastTestsFailed.log`. The redirected
  console log stopped earlier and is not the complete batch transcript.
  Separate unchanged-budget serial verification passed, exit 0: lifecycle
  4 cases in 93.59 seconds, authority 6 cases in 71.87 seconds, 165.48 seconds
  total. Raw log: `/tmp/lmdj-witness-checks-isolated-v1.log`. Across the final
  batch and this explicit follow-up, all 19 selected groups have passing
  evidence (71 cases), without reclassifying the first batch's exit 8.
- The preliminary direct 11-case run had 10 passes and one error, exit 1:
  `/tmp/lmdj-witness-checks-contract-v2.log`. It preceded the final authority
  sanitization patch and is not exact-final-code proof. Its history-deletion
  reader case passed in the final configured batch; the original underlying
  preparation error remains undetermined, not inferred from later success.
- First complete-Portal rehearsal failed, exit 1, in the initial snapshot
  `check:current`, before the new witness runner. Actual child output reports
  `ENOSPC` while writing Portal build routes. Retain
  `/private/tmp/lmdj-witness-checks-portal.M9xFqR/run-v1`, specifically
  `logs/executed-ay6utkaf.log`, and outer
  `/tmp/lmdj-witness-checks-portal-v1.log`. No journal replay or cleanup was
  performed. Available space subsequently recovered without this Task deleting
  anything; that observation does not establish causes of the other failures.
  The separate fresh-fixture complete rehearsal subsequently passed, exit 0, in
  `/private/tmp/lmdj-witness-checks-portal-v2.ttZzA7/run-v1`, outer log
  `/tmp/lmdj-witness-checks-portal-v2.log`. It retains actual snapshot generation
  and resume, both cut phases, actual squash, official witness generation and
  cold verification, both witness Task phases, cold Task with zero new command
  executions and unchanged history, witness squash and source-absent fresh-clone
  Portal verification. The final Portal ran 170 tests, all passed, zero skipped;
  47 routes and internal links were valid. This is a new fixture environment,
  not replay or reenrollment of the failed original command journal.
- Independent complete-diff review found and verified the callback-error
  sanitization repair. Separate static review of external
  `/tmp/lmdj-witness-checks-audit.py` found and verified a repair to authenticate
  all six complete command vectors, including the original whitespace base,
  and independent 2/6/3/6 output populations. The audit actually refuses the
  incomplete rehearsal and Python `-O` (both exit 1). Its subsequent actual
  successful-run audit passed, exit 0, in
  `/tmp/lmdj-witness-checks-audit-v1.log`: 21 outer commands (19 successes plus
  two expected source-object absences), 17 actual spools whose complete byte
  lengths and digests match their executed results, including six exact Task
  vectors. Static approval is not substituted for this execution evidence.
- Final staged ownership/admission check passed 74 tests, exit 0, in
  `/tmp/lmdj-witness-checks-scope-v2.log`.

The successful rehearsal records base/control revision
`634ffc7878c3e6ef84332903cadd9af84d191e74` separately from the actual WIP
controller and harness byte hashes; it is not a claim that the new controller
already existed at that base. Fixture identities are source
`8ee4b7fe3d7abe73122a46a3478c6ead0c2922a7`, cut
`fe23d4a64a31512c0c9f8a69955ab460910fdf6c`, introducing squash
`afae4827843fc4e36b94ed3012d39129ebc6fa9b`, witness Task
`cd70b4b6e8059366e0744f8269175b897ffeda95`, and witness squash
`bb47b8d4d22f85c1ee2e9311d76662de8556bb6e`. Task checks bind digest
`ab14c89ccf4a9b86e532e37eb89e826fc68852468eb7dd701e3d6e7ae83043ce`.
The fixture Build `1.0.57.0` is not a real Product allocation. Production parent
composition, actual remote review, complete CI, signing, publication, live
changelog site, both Host deployments, promotion and full release acceptance
remain outstanding in the original objective.

Retained initial fixture failure: the first lifecycle test incorrectly assumed
that successful Git whitespace checking emitted zero bytes. Actual Git emitted
a 311-byte graft deprecation hint with exit 0. The fixture now authenticates
actual captured output instead of assuming silence; the command, budget and
exit requirement are unchanged. Raw failure remains in
`/tmp/lmdj-witness-checks-lifecycle-v1.log`.

Pitfall disposition: no new ledger entry. The output-assumption and callback
sanitization defects are expressed by focused regressions; the isolated disk
exhaustion is retained as operational evidence without inventing a new policy
or an unproved cause for the other failures.
