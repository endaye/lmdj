# Review discovery: distinguish run creation from attempt creation

Baseline: `9579b8ea` on 2026-09-08. One narrow implementation Task;
local verification and commit are authorized, shipping remains on HOLD.

## Declared files

- `scripts/ci/review_discovery_runtime.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- This plan.

No workflow, storage identity, reducer/schema, collector, scheduler or product
source changes. No initialization, dispatch, cancellation, business write or
release operation is part of this Task.

## Read-only evidence and defect

A finite legacy migration audit read all Core CI workflow `313388832` runs
from first producer `22247897e9163a3f34e15f564bec133419d1f177` at
`2026-09-07T12:20:36Z` through `2026-09-08T00:25:37Z`: 38 runs and all
41 exact attempts. The actual run-list API retains original run creation time;
the exact-attempt endpoint can expose a later creation time:

| Run / attempt | Inventory created_at (UTC) | Exact-attempt created_at (UTC) |
| --- | --- | --- |
| [34124875948 / 2](https://github.com/endaye/lmdj/actions/runs/34124875948/attempts/2) | 2026-09-07 12:59:28 | 2026-09-07 13:00:27 |
| [34133798298 / 2](https://github.com/endaye/lmdj/actions/runs/34133798298/attempts/2) | 2026-09-07 14:35:38 | 2026-09-07 14:36:33 |
| [34137826864 / 2](https://github.com/endaye/lmdj/actions/runs/34137826864/attempts/2) | 2026-09-07 15:20:49 | 2026-09-07 15:21:28 |
| [34137319062 / 1](https://github.com/endaye/lmdj/actions/runs/34137319062/attempts/1) | 2026-09-07 15:15:00 | 2026-09-07 15:15:01 |

Raw paginated inventory and all exact-attempt documents are retained locally in
`/tmp/lmdj-legacy-migration-audit.wVesVj/`. These are real Core CI API samples,
not a claim that these runs are PR Review producers or that a live PR Review
callback was already lost. The shared Actions endpoint shape exposes the
discovery fixture's false assumption. No historical events were modified.

## Narrow time semantics and unchanged authority

Keep the original inventory timestamp immutable in the protocol. Generic-run
metadata must still match it exactly, so later reruns never move the run into a
new scan window or replace attempt 1. Exact-attempt metadata must contain a
valid timestamp at or after that original run creation time; it need not be
equal, even for attempt 1. Earlier or malformed timestamps remain unresolved.
There is no arbitrary tolerance window: a valid rerun can occur much later.

Time does not prove source identity. Preserve exact run ID, exact attempt,
repository numeric ID/name, workflow ID/path, event and head validation; the
unchanged real collector independently validates source/control, jobs, artifacts,
historical policy and the complete result. A timestamp adjustment cannot queue
another head's receipt. Frozen Outbox payload equality and queue-only semantics
remain unchanged. No schema migration or old record rewrite is required.

## Minimum verification and journey

Use the existing actual Runtime/Journal/collector/Outbox HTTP fixture journey:

1. A first attempt offset by one second still queues its exact authenticated
   failure while preserving original run time/frontier and doing no business POST.
2. A valid second attempt offset by 59 seconds preserves attempt 1 and the
   original time, queues a second distinct observation, and a fresh process
   replay adds no duplicate Outbox event.
3. Before-origin/invalid timestamps and wrong run/attempt/workflow/repository/
   head identities stay unresolved with no queued report.

Baseline 21 bridge tests passed. Adding the first/second attempt timestamp
cases produced two red failures (`unresolved` instead of `failure-queued`)
before the implementation fix. After the fix, all 24 bridge and 49 pure
protocol tests passed. Final full CI contract discovery with pinned actionlint
passed 1,644 tests in 40.940 seconds; staged ownership passed 66 tests and
staged whitespace validation passed. The actual precommit Portal check exited
1: 57 initial tests, 54 passes and three missing dependencies (`glob`,
`gray-matter`, `cheerio`). Downstream Portal checks were not reached; this is
not a Portal pass. No threshold or test was reduced.

Follow-up verification installed the unchanged Portal lockfile with
`npm ci --ignore-scripts --no-audit --no-fund` (2,280 packages; no tracked
dependency or lockfile changes). The repeated Portal check passed all 65 initial
tests, then failed `validate:docs`: the baseline
`operations/version-and-release.mdx` classifies internal marker
`lmdj.release-plan-marker.v3` as an inactive Contract ID. Later Portal stages
were not reached. The root reports a separate T5 companion correction, not yet
on this Task's main baseline; it is deliberately not mixed into this narrow
timestamp fix. The actual result remains a Portal failure, not a pass.

Shipping preparation subsequently rebased this unpublished Task onto main
`aadb309c` (including #858, #860, #861 and #862) without conflicts. The
implementation, test and pitfall blobs were unchanged; the independent Portal
correction is now inherited, not copied into this Task. Repeated checks passed:
24 bridge tests, 49 protocol tests, 66 ownership tests and 1,657 full CI contract
tests in 37.514 seconds. With the locked dependencies already installed, the
complete `scripts/architecture-portal.sh check` now exits 0, including docs,
release-document checks, production build and build checks. Earlier failure
results above remain historical evidence rather than being rewritten as passes.
Authorization extends to push and PR only at this stage; merge remains with
the root after final-head review. No active full batch was cancelled or restarted.

These fixtures exercise the shared API shape with real local modules, not a
hosted PR Review rerun acceptance claim. Production deployment and an actual
authenticated PR Review attempt with distinct timestamps remain unexercised.

## Version Management

Version impact: none — an internal CI timestamp comparison changes no product,
component, contract or stored discovery schema identity.

## Documentation Impact

Documentation impact: none — internal CI logic, regression and plan only;
no Architecture Portal routes, diagrams or projected identities change.

## Pitfall impact

Recurrence of `fake-tool-stub-strictness`: a real external API field was
incorrectly identical in the fixture. Record this occurrence as self-reported
Codex. The narrow regression covers this API-time invariant; the existing
broader escalation #726 stays open and is not absorbed by this Task.
