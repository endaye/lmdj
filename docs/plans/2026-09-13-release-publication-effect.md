# Verify the managed publication's actual effect

Status: delivery integration of original `70519dd8` onto the actual managed
adapter squash `2da0a62a` (PR 1294). Current default-clock refresh, final expiry checks, ZIP bounds and
durable state-capacity checks are retained. Historical original-stack results
below are not current delivery verification.

## Scope

Declared files:

- `tools/release/publication_effect.py`
- `tools/release/dispatch_evidence.py`
- `tests/build/release_publication_effect_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-publication-effect.md`

Build on reviewed managed adapter delivery `2da0a62a`.
Implement the actual read-only publication effect callable for DispatchTransition.
Authenticate the original parent/operation and independently reverify the full
correlation binding. Require successful exact run/attempt and both actual
preflight/publish jobs with matching run, attempt and control, then use the existing
`collect_publication_state` verifier: canonical authority, signed tag, complete
asset verification, exact plan/Release metadata and frozen changelog remain
owned by the existing release pipeline. Compare the actual record to the frozen
candidate target and both changelog/notes digests. Reauthenticate correlation
and run outcome after Release verification before returning record-bound proof.

The trusted parent must still derive the frozen expected projection from its
verified candidate, supply original authorization/readiness and select the
canonical production PrepareContext. Constructor inputs are not authority.
No live backend or service is installed; no publication/deployment is requested.
A pending run yields pending, failed run yields conflict even if publication
may have happened, unknown/verifier exception yields unknown (never absence).
The operator must reconcile failed publication rather than repost. No later
deployment is authorized by this callable. Historical record digest is stable
while the ledger moves from releasable to published; actual drift still refuses.

## Verification

Real dispatch consumer and temporary Git, actual release preparation/publication
verification functions over the existing fake Git/GitHub/profile fixture. Bind
actual fixture tag/Release ID/plan/notes to the receipt rather than stubbing the
collector. Test pending/failed run, wrong receipt or candidate, body/asset/date
drift, changing attempt during verification, repeated observation and published
ledger handoff. Connect the callable to actual DispatchTransition observation.
Fixture source/signatures/provider checks do not establish cold signer, live
GitHub, full candidate CI, production deploy or unattended acceptance.
Run focused CTest contracts, existing dispatch/publication/managed regressions,
staged ownership and Portal check; obtain independent review before commit.

## Version Management

Version impact: none

Reason: internal read-only release verification; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document actual publication effect integration and remaining scope.

## Current delivery verification

The old constructor-clock defect discussed below was already repaired in the
delivery prerequisites. Independent review found a distinct outer boundary:
the final real run/jobs reads could consume the remaining artifact lifetime
after the last correlation read had checked it, yet the effect still returned
verified. A new actual-fixture test first failed (exit 1, 5.154s): two successful
real outcome reads with expiry reached after the second still returned verified.

The authenticated correlation binding now carries `artifact_expires_at` from
the actual API artifact, covered by the complete inventory reread and binding
equality check. After all remote outcome reads, the effect checks that deadline
locally against the consumer's current clock before returning proof. The field
also enters the parent correlation/effect digest. Old bindings lacking the
field refuse or conflict rather than silently acquiring a new proof.

Fixed local results, all exit 0: effect 17/17 (15.267s), dispatch evidence
34/34 (7.303s), managed dispatch 19/19 (9.513s); existing publication 10/10
(0.188s). Configure dev with Python 3.14.7 succeeded. The four registered
effect/managed-dispatch/dispatch-evidence/publication contracts passed in
34.81s with unchanged individual timeouts. Independent amendment review
reran effect 17/17 (16.791s) and found no other actionable finding in all six
files; the actual publication collector was never stubbed.

Node 22.22.2 with locked dependencies: Portal check exited 0, including
144 tests, diagrams, snapshot/typecheck/changelog validation, optimized build
and 47 routes/internal links. Output:
`/tmp/lmdj-publication-effect-delivery-docs-v1.log`. Staged ownership/admission
also passed; output: `/tmp/lmdj-publication-effect-delivery-scope-v1.log`.

These source/fixture results do not prove real signatures, live candidate CI,
GitHub publication, deployed Sites, service cold start or complete unattended
acceptance. Pitfall disposition: no new process entry; the real-read clock
regression fully expresses the invariant without adding a general CI gate.

Final dependency integration uses actual PR 1294 squash `2da0a62a`, including
its independently corrected parent PR guard and callback-error sanitization.
This Task's source, tests and CMake bytes are unchanged from `ff9f9d78`; Portal
retains both the inherited guard paragraph and this effect paragraph. Independent
complete six-file rebase review found no actionable finding.

After rebase, effect 17/17 (17.648s), managed PR 26/26 (0.493s), managed dispatch
19/19 (9.617s) and dispatch evidence 34/34 (7.423s) all exited 0. Final ownership
74/74 (10.531s) and Portal check also exited 0; the latter verifies 144 tests and
47 routes under Node 22.22.2. Retained outputs:
`/tmp/lmdj-publication-effect-delivery-scope-final-v1.log` and
`/tmp/lmdj-publication-effect-delivery-docs-final-v1.log`.

## Historical original-stack verification results

- Actual publication effect suite 16/16, exit 0
  (`/tmp/lmdj-publication-effect-tests-v2.log`); first 13-case iteration also
  passed and remains in `-tests-v1.log`.
- Configure dev exit 0. Registered CTest contracts 4/4, exit 0: publication
  effect, managed dispatch, dispatch evidence and publication
  (`/tmp/lmdj-publication-effect-ctest.log`).
- Staged path ownership/admission 74/74, exit 0
  (`/tmp/lmdj-publication-effect-scope.log`).
- Fresh npm ci and Portal check with Node 22.22.2: exit 0, 139/139 tests and
  47 routes/internal links (`/tmp/lmdj-publication-effect-docs.log`).
- Independent `release_journal_review` agent inspected all six files, then
  rechecked the final actual-job checks against the workflow and reran 16/16,
  exit 0, with no actionable findings. Earlier independent regressions also
  passed: publication 10/10 and dispatch evidence 30/30. No external writes.

The positive fixture now includes both successful actual workflow jobs; the
three one-fact counterexamples reject failed preflight, missing publish and
wrong publish attempt even when the aggregate run claims success. The collector
is never stubbed; its lower Git/signing/profile dependencies remain synthetic
and must not be represented as real signature or candidate acceptance.

Pitfall disposition: the effect-binding invariants are directly regression
tested, so no new process-ledger entry is needed. A separate source inspection
found the existing dispatch and Site readers freeze default `now` at construction;
a long-lived service could therefore use stale artifact-expiry time. Repair
and fault-test that lifecycle before production service acceptance. This Task
does not discharge that gap, nor the original authority/candidate/Host effect,
CLI/service, full-journey rehearsal and actual-release acceptance gaps.

A read-only local advancing-clock experiment confirmed that gap: the default
dispatch reader created on simulated 2026-09-13 still accepted the same fixture
artifact (expires 2026-10-13) on simulated 2026-11-13. The receipt remained
identical; the retained constructor clock, not the actual later clock, determined
acceptance. No GitHub state or real machine clock was changed. This is a
reproduced source defect to fix next, not a production-expiry incident claim.
