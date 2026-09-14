# Managed release dispatch transitions

Status: delivery integration of original `f75b827f` onto durable controller
`f576b610`, with the shared state-size limit, clock/ZIP protections and existing
Task-verification CTest registration preserved. Historical original-stack
results below do not establish current delivery verification.

## Scope

Declared files:

- `tools/release/durable_dispatch.py`
- `tools/release/dispatch_transition.py`
- `tools/release/orchestration_driver.py`
- `tools/release/evidence_pr.py`
- `tools/release/evidence_pr_transition.py`
- `tests/build/release_managed_dispatch_test.py`
- `tests/build/release_managed_pr_transition_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-managed-dispatch.md`

Build on the reviewed durable controller delivery `f576b610`.
Separate optional private enrollment and remote read-only observation from the
first durable POST, then connect the concrete controller to ReleaseDriver for
publication, Runtime and Creator. Parent intent must precede child advancement;
after parent enrollment missing child storage is unknown, never reenrolled.
Existing child intent is never resent. An unattempted enrolled child can make
its first POST after a parent crash. Correlation alone cannot complete a step:
a mandatory separate read-only effect verifier must pass for that exact binding.
The parent evidence digest binds both correlation and effect evidence.

Original authority/readiness remain mandatory. A trusted scope binder must
resolve candidate/Draft/Host prior from independently verified parent evidence;
the adapter also enforces request digest, operation, workflow/step, actor and
explicit tag identity. This task does not implement the production authority,
scope or effect verifiers, select a live backend, install a service, add public
run/status/resume commands, or execute an actual release/deployment. Those
remain required for the full single-command release objective.

## Verification

Use real parent and child journals, actual dispatch consumer/client, temporary
Git and fake HTTP. Assert POST sees both durable intents; observation never
POSTs; pending effect blocks later legs; delayed receipt recovers only the
original operation; process death before child POST or after remote acceptance
does not duplicate a write; missing child state is never recreated; changed
scope, authority and previous evidence block progress. Test actual workflow
mapping for all three steps, independent effect refusal and stable revalidation.
Other release legs and effect verifiers remain explicit fixtures, not production
publication/deployment or complete 16-suite evidence.
Run new contracts, existing durable dispatch/driver/managed PR regressions,
staged ownership and Portal check, then independent read-only review.

## Version Management

Version impact: none

Reason: internal release orchestration only, no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document parent/child dispatch behavior and remaining production gaps.

## Current delivery verification

The CMake insertion conflict was resolved by retaining the existing
Task-verification contract (60s) and independently registering managed dispatch
(30s). The prerequisite's shared state read/write bound and both capacity
regressions remain intact. The initial integration needed no source repair;
the later online review identified the additional boundary defect below.

Current local results, all successful commands exited 0:

- Managed dispatch 19/19 (9.162s); durable dispatch 19/19 (4.204s).
- Driver 13/13 (0.198s); managed PR transition 17/17 (0.370s).
- Dispatch discovery 34/34 (7.582s); GitHub API 39/39 (0.013s);
  orchestration journal 21/21 (0.157s).
- Configure dev with Python 3.14.7; the four registered managed-dispatch,
  durable-dispatch, driver and managed-PR contracts passed in 16.42s with
  unchanged timeouts.
- Staged ownership/admission 74/74 (6.084s), retained at
  `/tmp/lmdj-managed-dispatch-delivery-scope-v1.log`.
- Node 22.22.2 with locked dependencies: Portal check exited 0 with 144 tests,
  diagrams, snapshot, typecheck, changelog validation, optimized build and
  47 routes/internal links. Output:
  `/tmp/lmdj-managed-dispatch-delivery-docs-v1.log`.

An initial command used the nonexistent `release_managed_pr_test.py` filename
and exited 2 without running that suite. The actual registered
`release_managed_pr_transition_test.py` was then located and run successfully;
the missing-file invocation is not counted as verification.

Independent complete seven-file review found no actionable finding and reran
managed dispatch 19/19 (11.078s), durable 19/19 (4.463s), driver 13/13 (0.251s)
and managed PR 17/17 (0.374s), all exit 0. These tests use real nested journals
and process-crash entrypoints, but effect verifiers and the other release legs
are fixtures. This is not production composition, full-suite, signing,
deployment, service cold-start or complete unattended release acceptance.
Pitfall disposition: no new process entry; executable regressions express the
invariants without adding a general required CI gate.

## PR 1294 review correction

The online review of `451107a3` identified that the managed publication PR
path lacked the final parent guard already supplied to dispatches. An independent
reviewer reproduced all four create/merge x revoked-authority/replaced-parent-lock
cases through the actual nested controllers and GitHubClient fixture. Root then
added permanent regressions: all four failed on unchanged source (0.071s), because
POST/PUT still occurred after the fault. This preexisting path is in the managed
driver's safety scope and is repaired here rather than waived.

The controller now calls an optional parent guard after its final preflight and
numeric PR read, immediately before each POST/PUT, then rechecks its own writer.
The managed PR adapter requires a callable guard; the driver supplies the same
parent authority/writer validation used by dispatch. Guard failure retains the
durable child intent, and reopening does not replay it. Four causal regressions
assert both refusal and unchanged retained state on resume; two more replace the
child lock inside the parent guard, and one rejects a missing callable. The old
opaque-backend comparison uses an explicit fixture authority callback, not a
production authority claim. No timeouts, protections or coverage were relaxed.

The other two online findings were independently rejected using actual fixtures:
Observation evidence is strictly validated as sha256/reference strings, and fork
assignments do not change the parent process or fresh unittest instances. These
dispositions do not replace review of the corrected head.

Independent correction review found that the new public child callback could
leak its exception text when it raised the controller's own EvidencePrError.
Two actual child-entrypoint regressions failed (2 errors, 0.010s); a shared guard
wrapper now sanitizes all ordinary callback exceptions before either transport
write. Deliberate process-death BaseExceptions retain crash semantics. This
finding was not hidden by relying on the parent's outer exception handling.
Final correction verification, all exit 0:

- Managed PR 26/26 (0.513s), standalone PR 36/36 (0.115s).
- Managed dispatch 19/19 (9.147s), driver 13/13 (0.201s).
- Actual registered CTest driver/managed-dispatch/durable-dispatch/managed-PR/PR
  contracts 5/5 (17.98s), unchanged budgets.
- Portal check under Node 22.22.2 exited 0; retained output is
  `/tmp/lmdj-managed-dispatch-delivery-docs-parent-guard-v1.log`.
- Independent complete ten-file review found no remaining actionable finding;
  final managed PR suite independently passed 26/26 (0.461s).

The initial seven-file clean review did not detect the PR guard gap; retain that
limitation and the failed iterations above. Current-head online review is still
required after committing the correction. No formal release or business workflow
was dispatched.

## Historical original-stack verification results

- Managed dispatch suite: 19/19, exit 0
  (`/tmp/lmdj-managed-dispatch-tests-v3.log`).
- Existing durable dispatch 17/17, driver 13/13 and managed PR 16/16, all exit 0
  (`/tmp/lmdj-managed-dispatch-durable.log`, `-driver.log`, `-pr.log`).
- Configure dev exit 0; actual CTest registration/execution 4/4, exit 0
  (`/tmp/lmdj-managed-dispatch-configure.log`, `-ctest.log`).
- Staged new-file ownership and admission: 74/74, exit 0
  (`/tmp/lmdj-managed-dispatch-scope.log`).
- Portal check: 139/139 tests, 47 routes/internal links, exit 0
  (`/tmp/lmdj-managed-dispatch-docs.log`), after fresh npm ci with Node 22.22.2.
- Independent `release_journal_review` agent inspected all seven files and the
  final four additional regressions: no actionable findings. Independently
  reran the final managed suite 19/19, exit 0; no external services or edits.

Preserve `/tmp/lmdj-managed-dispatch-tests-v1.log`: eight fixture assertions
failed because the POST observer read the parent envelope as its inner state.
Reading the actual envelope's `state` fixed the fixture; production journal
checks were not relaxed. The first corrected run was 15/15 in `-tests-v2.log`.

The final transport guard now also rechecks parent writer and authentication,
alongside child writer, original authorization, readiness and scope binding.
Tests fault that boundary causally; a replaced parent lock, lost parent authority
or changed scope leaves a durable unresolved intent and sends zero POSTs.

Pitfall disposition: these are directly testable controller invariants with
regression coverage, not new process knowledge requiring a ledger entry.
The full goal still requires production scope/authority/effect composition,
candidate allocation, signing, service/CLI recovery, all release journey legs,
real-candidate acceptance and guarded shipping. The prerequisite PR #1266 was
read live during this Task: OPEN, unmerged, head
`c8fab3b67b6abe3bff708b5563acfc84b0e9e671`; no owner adoption was invented.
