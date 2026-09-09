# Discover durable test results through the existing Canary planning entry

Status: source implemented and locally verified; live activation remains separate.
Part of result-driven delivery.

## Task and declared files

Connect automatic result discovery to the existing authenticated planning entry,
not another planner, queue or scheduler. Add one bounded `reconcile-next`
operation to the same workflow used for manual observation/recovery.

- `tools/canary/planning_entry.py`
- `.github/workflows/canary-planning.yml`
- `tests/build/ci_canary_planning_entry_test.py`
- this plan
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`

## Behavior and authority

An authenticated completed Self-test Report workflow is only a wakeup hint.
Read complete authenticated scheduler state, never caller-supplied results or
the triggering workflow's green/red conclusion. Prefer recovery of the original
unfinished planning intent. Otherwise select one terminal source not already
recorded by the existing planning observations, in stable scheduler order.
Retain ignored failed/missing/not-required and explicit nonautomatic sources;
none grants model execution, a successful plan or deployment evidence.

Use existing `Plans.begin/finish` and `plan_after_result`; preserve frozen inputs,
complete decision bytes, active target and newer pending coalescence. Complete
observation is the durable discovery receipt. Do not add a duplicate cursor
store. Repeated wakes after completion may discover the next source but cannot
replace the completed observation. An unfinished write always takes priority.

Manual `reconcile-next` uses the same implementation. Initialization and progress
bootstrap remain separate explicitly manual operations. Automatic work requires
an explicit default-off readiness variable and reviewed dedicated storage;
missing configuration or bootstrap never initializes storage or invents progress.
No repository variables, Issues, credentials or live journals are configured by
this Task. Existing Self-test Report health observations provide later recovery
opportunities when an immediate workflow chain is suppressed; the callback is
not assumed to be a reliable exactly-once transport. No daily product/deploy cron.
Automatic hints coalesce in their own workflow admission group without cancelling
running work. Manual commands retain separate admission identities; all writers
still share the existing short controller lock, not a heavy-work workflow lock.

Missing version baseline remains `None` with bootstrap full scope. Do not use a
test interval base, root commit or target as fictional version-accounted history.
Assessment claim linkage, first baseline adoption, plan retirement, version/site
progress, version allocation, PR creation and deployment remain later work.

## Verification and far-side evidence

Start with failing no-source-ID discovery and unfinished-priority regressions.
Use real scheduler and planning Journal composition: discovery -> durable intent
and complete observation -> fresh process replay of complete bytes and identity.
Exercise duplicate/late/newer wakes, ignored failure/missing/no-test results,
source loss after completed persistence, moving main during partial recovery,
lost intent/chunk/complete responses, and subsequent next-source discovery.
Every leg must assert the durable far-side state; no scheduler writes, model
invocations or progress advancement are allowed. Missing or malformed source
and pending scheduler checkpoints fail without repair. Wrong workflow, repository,
attempt, callback identity, lock, missing readiness/storage/bootstrap and injected
caller evidence cannot write plans. Preserve all manual operations.

Run focused planning suites, complete canary/CI regression, ownership checks,
workflow actionlint with ShellCheck and the existing exact queue-key compatibility
exception, Portal check and final committed-range/PR declarations. The live
automatic discovery/recovery endpoint remains unaccepted until separately
authorized storage configuration and an actual run prove it; local API fixtures
do not establish token scopes, workflow chain delivery or live journal identity.

The callback field inventory was checked against the
[Octokit workflow-run schema](https://github.com/octokit/webhooks/blob/main/payload-schemas/api.github.com/common/workflow-run.schema.json)
and its completed-event example, including required repository projections.
This checks the fixture's field shape, not actual Actions delivery or token scopes.
Automatic recovery still authenticates the current callback and scheduler
configuration before using the frozen intent; manual `recover` remains available
if that automatic prerequisite is unavailable. Oldest-first discovery intentionally
stops at unreadable historical evidence; initial backlog/throughput requires live
acceptance rather than an invented skip or a claim that one wake drains all work.

Local verification on September 9:

- Entry: 34 tests passed; unchanged planning Journal: 19 passed. Independent
  review reran both suites. Red-first tests reproduced missing discovery and
  unfinished-priority behavior; callback omissions were also rejected by the
  final source after their negative regression first failed.
- Complete `ci_*_test.py` discovery: 2,193 passed, no skips, with actionlint
  available. The final run includes the stricter callback repository checks.
- Staged new-file ownership: 66 passed. Product version verification passed
  unchanged; no Build or snapshot was allocated.
- Portal: 112 tests passed, production build and all 44 routes/internal links.
  Dependencies were supplied with the canonical `scripts/docs-site.sh install`.
- Actionlint 1.7.12 with ShellCheck 0.9.0 passed the changed workflow using only
  the existing exact concurrency.queue compatibility exception. Its actual
  queue modes and expressions are independently asserted by the workflow tests.
- Repository variable inventory was read-only checked: neither new automatic
  readiness nor planning storage variable was present. No configuration, storage
  initialization, backend invocation or live planning dispatch was performed.

## Version Management

Version impact: none

Reason: CI planning discovery only; no Product/Host/Module/Provider/Contract,
Assembly, version or snapshot identity changes.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/testing-and-proof/

Document the shared manual/automatic recovery entry, disabled switch and its
strict planning-only boundary. Do not present observation as deployment.
