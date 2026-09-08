# T4g — Real short-lock batch runtime

## Declared files

- `scripts/ci/batch_runtime.py` (new)
- `tests/build/ci_batch_runtime_test.py` (new)
- `scripts/ci/batch_controller.py`
- `tests/build/ci_batch_controller_test.py`
- This plan.

## Scope and authority

Compose the actual GitHub HTTP transport, fixed-Issue journal, real complete
Git history, controller and scoped-verdict validator. This Task does not edit
workflows, dispatch anything, create Issues, publish reports, change permissions,
switch automatic triggers or allocate a release. Root owns caller workflow and
future report/outbox integration; T4f owns reusable product execution.

`init`, `reconcile` and `settle` are real CLI entries. Every invocation requires
the main first-attempt run, frozen checkout, exact controller job and externally
held short writer lock. `reconcile` can return execute only after a committed
claim. `settle` disables execution, including recovery of this same live run's
admit-without-claim; it still persists genuine terminal results and progress.
The CLI refuses an existing output file rather than exposing a stale action.

Config is closed: repository, issue_number, issue_node_id, bot_node_id,
workflow_id, epoch. Environment is GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID,
GITHUB_RUN_ATTEMPT=1, GITHUB_SHA, GITHUB_REF=refs/heads/main and
BATCH_WRITER_LOCK=self-test-report. Controller job name is
`Incremental batch controller`. The sentinel checks caller wiring; GitHub does
not provide an independent lock-ownership proof. Workflow job-level concurrency
must provide it and must release before the heavy DAG starts.

Initialization is an explicit operation on the fixed open Issue with exact
body `<!-- lmdj-ci-journal-uninitialized-v1 -->` followed by one newline and no
comments. It performs one PATCH, then rereads actual bot/editor metadata and
the empty journal. Unknown response stops; normal reconcile never creates or
resets state. Empty checkpoint creates no processed/healthy baseline. Shared
repository-controlled Actions bot trust remains the T3/T4b assumption, not
cryptographic attribution of a write to a particular workflow.

## Execution and retained evidence

Caller display name: `Execute incremental batch`; producer suffix:
`Scoped batch verdict`. Exact artifact `batch-verdict-<target>-<run>-<attempt>`
has exactly verdict.json, execution.json and needs.json. Validate the complete
API run/attempt and jobs, immutable request, complete current/historical policy,
execution projection, recomputed needs verdict and exact product API names.
No slash-suffix guessing: `Docs / static` and nested reusable names are literal.

Judge and upload steps must succeed. The producer may correctly fail its final
business-status step when selected work failed; this is not an artifact error.
The reviewed macos-primary job-level continue-on-error is the sole exception to
direct raw API/needs success equality. T4f's dependency mapping uses change-scope
and explicit macOS dependencies, not legacy pre-heavy serial dependencies.

Successful-upload visibility lag is pending, not missing. A complete artifact
inventory with no matching artifact becomes missing only after the API upload
step/job completion plus the fixed 30-day retention window, measured with the
controller's UTC clock. It is then no acceptable retained evidence, not a claim
that the physical object never existed. Explicit artifact expiry or terminal
execution without successful evidence upload is also missing.
API failure blocks rather than inventing absence. The complete validated verdict
is bounded/compressed inside result.reference, preserving mixed product failures
and uncovered jobs after artifact expiry. Once terminal run/source, successful
judge/upload and completed download are authenticated, permanently invalid ZIP,
closed JSON or contradictory frozen content is missing coverage, allowing finite
settlement with debt. The retained artifact remains available for inspection;
diagnostics do not echo its contents. API/identity/download uncertainty and a
valid verdict exceeding the durable reference budget still block, never pass.
Report/outbox writes are intentionally absent: the legacy
reporter's in-memory unknown-write fence is not cross-process persistence.

GitInputs uses the merged actions/contents-only MergeMapReader. Repository and
PR Review workflow IDs come from independent API reads, not config/artifacts;
missing mappings or API access conservatively select full. No PR endpoint or
second model call is made. The actual reader's missing-map path and explicit
advice forwarding are tested; remote valid-map routing remains O1 evidence.
Manual candidate requests keep their frozen original identity across redelivery;
their completion is settled without automatic admission when using `settle`.

A queued request can retain old control while its executor uses newer main.
Historical policy remains bound to the frozen request. Execution compatibility
compares bytes of self-test-report.yml, ci.yml, core-nightly.yml and
architecture-portal.yml at both independently verified main-history controls.
T4f performs the same closed check before publishing heavy admission outputs.
Known source incompatibility fails that preflight; only after the actual run
terminates does this runtime record missing coverage and release its request
slot. It does not invent a terminal state or globally block subsequent work.
Explicit re-recording/migration of incompatible requests is a future operator
path, not automatic substitution of a different control revision.

## Verification and remaining acceptance

Lowest tier: `ci_batch_runtime_test.py` and `ci_batch_controller_test.py`, then
GitHub journal, execution, verdict, scope and staged ownership regression suites.
Four settlement-only tests were observed red before implementing the switch.
Real temporary Git + strict source-shaped HTTP fixtures exercise initialization,
claim, terminal evidence, persisted result, restart without artifact, mixed debt
and failure, lost claim/admit response, existing Issue rejection, paging failure,
missing/expired evidence, and explicit command redelivery. These are local
protocol checks, not actual remote mutations or proof of platform permissions.

O1 must verify real bot editing, token/lock boundaries, nested job names,
continue-on-error API projections, ZIP contents, delayed visibility and complete
workflow_run/tick wakeups. Current light job completion is not whole-run
termination. Existing daily entries remain unchanged until T5's separate cutover.

## Documentation Impact

Documentation impact: none — internal runtime and tests, no Portal pages,
projected identities or enabled automatic scheduling changes.

## Version Management

Version impact: none — no Product Build, Module, Host, Provider or Contract
version changes; internal CI record schema is not a product release.

Pitfall impact: none — existing fake-tool, platform-side-effects, immutable
identity and visible-failure guidance applied; local fixtures are not invented
production incidents or evidence of completed O1 acceptance.

Root review found two recovery edges; regressions were observed red before
the fixes. First, pending light controller wakes must not starve bootstrap.
Only same-source, same main workflow first-attempt runs with complete jobs
showing the sole never-started queued controller and only terminal skipped
siblings (or not-yet-started run with no expanded jobs) are excluded under the
shared short-lock invariant. An already-started/completed controller, any other
active/successful/unknown job, unknown source or an active run
with no visible jobs still blocks; old Core CI is never excluded this way.
Second, a successfully uploaded but subsequently removed artifact need not
leave an expired API object; the retention rule above prevents permanent pending.
Real lock ordering and API job visibility remain O1 checks, not fixture claims.
Follow-up red/green cases cover the real skipped legacy reporter sibling, bad
ZIP, wrong target and invalid digest. A separate regression preserves terminal
failed-upload plus complete empty inventory settlement; requiring a successful
upload before inspecting absence would wedge that recovery path. API download
failure remains unknown, and valid mixed failure/debt evidence remains complete.

Local verification on base `064531e63bc28e19422bc59498d3c8522d88e136`:
44 runtime tests, 43 controller tests, complete CI discovery 1264 tests
(one existing skip), and 66 staged ownership tests passed.
