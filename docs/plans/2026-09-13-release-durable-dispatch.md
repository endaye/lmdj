# Persist release dispatch before its sole POST

Status: delivery integration of original `ccdb4127` onto recovery consumer
`b10c1a78` (PR #1292, pending at Task start). Current clock/ZIP protections and
existing Task-verification CTest registration are preserved. Historical
original-stack results below are not current delivery verification.

## Scope

Declared files:

- `tools/release/durable_dispatch.py`
- `tools/release/github_api.py`
- `tests/build/release_durable_dispatch_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-durable-dispatch.md`

Connect the R4 authenticated receipt discovery to private durable operation
storage and one closed main workflow dispatch. A trusted parent must allocate
one canonical directory per operation, bind the original request digest and
unique operation ID, and supply original authorization and effect readiness
verification. This internal controller does not accept approval flags from
artifacts or implement the parent request service, global tag/Site exclusion,
signer configuration, release/deployment readiness or effect acceptance.

Newly created directories alone may enroll state. Existing directories are
resume-only; missing/corrupt state never resets an operation. Bind the complete
closed specification to a private canonical fsynced record under RequestJournal's
exclusive owner/process/thread/path-identity lock. Before any POST, collect the
complete workflow run inventory twice and freeze its run IDs atomically with
the intent. Recheck original authority and active writer at the final write
boundary, after transport-side actor/repository/workflow/protected-main reads.

Only three workflow names and their existing closed exact input schemas may
be sent, always on ref main. A 204 is not completion. After any transport
attempt, including rejection/timeout, preserve the intent and only discover
the original run using the persisted baseline. Never dispatch again from an
existing intent. Resume revalidates authority and actual far-side evidence;
no saved success bit is trusted. Missing evidence remains unknown. A crash
before intent persistence may still perform the first POST after recovery;
a crash after intent persistence is observe-only even if the POST never left.

Keep the two mandatory trusted gates distinct: `authorize` verifies original
authority/live protection on every call; `ready` verifies effect prerequisites
only before the first POST, including its final guard. Recovery must not
re-require a legitimately superseded pre-effect state (such as Draft after
publication). Read-only correlation still revalidates original authority.

GitHub dispatch has no expected-head CAS: main may advance between its last
read and POST. The existing workflow gates still apply; an actual run with a
different control SHA is refused by discovery rather than claimed as success
or retried. This controller does not claim to prevent that platform race.

## Verification

Actual private on-disk journal, actual GitHub client/consumer and temporary
Git with deterministic HTTP fixtures. Test normal dispatch/repeated start/
resume, accepted timeout, unobserved delivery, late receipt, missing/corrupt
state, changed scope, missing authority, replaced writer and concurrent writer.
Use real fork/exit for crashes before durable intent, after durable intent but
before POST, and after a file-backed simulated remote acceptance but before ACK.
Assert the durable bytes at the POST callback and reobserve the exact original
run after restart. These are local fault-injection facts, not real GitHub
publication/deployment acceptance. Register the test in root CMake; run selected
release contracts, GitHub API regression, staged ownership and Portal check.

Remaining integration: original authenticated request intake, effect-specific
authority/readiness implementation, parent driver adapter and durable service,
global resources, run/status/resume CLI, and full release/deployment journey.
Development does not dispatch an actual workflow or start a release.

## Version Management

Version impact: none

Reason: internal durable control behavior; no Product or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document durable no-replay behavior and remaining orchestration gaps.

## Current delivery verification

Independent review reduced a write/read capacity mismatch: the controller
could persist an intent larger than its 1MiB recovery limit and then send the
POST. A locally validator-accepted 900000-digit tag plus two complete 10000-ID
inventory reads produced a 1,100,664-byte intent in the review probe. This is
not a claim that GitHub accepts such a large dispatch input. It establishes
that locally admitted state could become unreadable before an external attempt.

Two permanent actual-controller/client/consumer regressions first failed
(2 tests, exit 1, 0.431s): oversized enrollment and baseline growth beyond the
reader's limit were not refused. `_save` now encodes once and checks the shared
read/write bound before creating a temporary file, writing those exact bytes.
The growth regression asserts unchanged original readable bytes, no intent,
no POST, and public resume retaining the same refusal. Independent amendment
review confirmed the fix and reran 19/19 tests (4.564s), with no further finding.

Current local results, all exit 0:

- Durable controller 19/19 (4.308s); authenticated discovery 34/34 (9.223s).
- Producer 12/12 (0.266s); Portal evidence consumer 22/22 (10.145s).
- GitHub API 39/39 (0.013s); existing orchestration journal 21/21 (0.160s).
- Configure dev with Python 3.14.7; four registered CTest contracts passed in
  22.88s with unchanged timeouts and existing Task-verification registration.
- Node 22.22.2 with locked dependencies: `scripts/docs-site.sh check` passed,
  including 144 tests, snapshot/diagrams/typecheck/changelog checks, production
  build and 47 routes/internal links. Output:
  `/tmp/lmdj-durable-dispatch-delivery-docs-v1.log`.

Raw causal failures remain in the tool transcript. These are local fixture
and actual process-crash tests, not real dispatch, service cold restart,
signing, publication, deployment or complete unattended release acceptance.
Pitfall disposition: the capacity invariant is fully captured by the regression;
no new process entry or general required CI gate is introduced.

## Historical original-stack verification results

- Durable dispatch: 17/17, exit 0 (`/tmp/lmdj-durable-dispatch-tests-v4.log`).
- Selected CTest contracts: 4/4, exit 0, including durable dispatch, authenticated
  discovery, receipt producer and changelog Site evidence
  (`/tmp/lmdj-durable-dispatch-ctest-v2.log`). Configure dev exited 0.
- GitHub API regression: 39/39, exit 0 (`/tmp/lmdj-durable-dispatch-api.log`).
- Staged path ownership: 74/74, exit 0 (`/tmp/lmdj-durable-dispatch-scope.log`).
- Portal check: 139/139 tests and 47 routes/internal links, exit 0
  (`/tmp/lmdj-durable-dispatch-docs-v2.log`), using pinned Node 22.22.2.
- Independent read-only review by the distinct `release_journal_review` agent:
  no actionable findings, including the final authorization/readiness split;
  independent final durable suite rerun 17/17, exit 0.

Retain the initial failed fixture run (`/tmp/lmdj-durable-dispatch-tests-v1.log`):
macOS `/var` resolved to `/private/var`, and the production canonical-path guard
correctly refused the fixture alias. Resolve the temporary fixture root; no
production guard was relaxed. Earlier successful iterations remain separate.

Pitfall disposition: the new durable-state and readiness invariants are expressed
directly in executable regression tests; no new process-ledger entry is needed.
These checks prove local source/fixture behavior only. They do not establish
real GitHub dispatch, signing, publication, deployment, full-suite acceptance,
protected approval, service restart or complete unattended release readiness.
