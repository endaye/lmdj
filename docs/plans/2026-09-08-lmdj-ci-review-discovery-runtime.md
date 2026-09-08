# PR Review discovery HTTP and Journal bridge

Date: 2026-09-08
Baseline: `e5412a4b1359dd928b556379c4195ffc05ed014d`
(C2 manual wiring main; no automatic activation).
Status: local implementation pending independent review and fixed configuration.

## One Task / five declared files

- `scripts/ci/review_discovery_runtime.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `scripts/ci/review_discovery.py`
- `tests/build/ci_review_discovery_test.py`
- `docs/plans/2026-09-08-lmdj-ci-review-discovery-runtime.md`

No workflow, automatic entry, shared storage manifest, scheduler/outbox reducer,
existing review consumer or journal transport is edited. This Task owns only
review discovery plus its necessary durable metadata-revisit cursor. It creates
no Issue and does not initialize, dispatch, cancel, execute products or release.

## Dependencies and fixed configuration

The independently owned `incremental_entry.load_storage(root, environment)`
returns the reviewed fixed scheduler/outbox pair from the current control Git
blob. Reuse that loader, never copy it or accept an operator path. Its landing
is a shipping dependency; this module's constructor fails closed if unavailable.

Read only `scripts/ci/review_discovery_storage.json` at the same exact control
Git SHA. Root owns that separate configuration Task. Its closed top-level fields
are `storage`, `source_floor`, `review_workflow_id`. Storage is the unchanged
Runtime six-field identity; source_floor is exact control_sha/created_at. Require
distinct discovery/scheduler/outbox Issue numbers, node IDs and epochs, with
the same repository, controller workflow and bot authority. Missing config is
an error, not permission to allocate or initialize storage.

The proposed oldest closed review producer is main
`0bcb14e9ada890f4c0e6b549f72dcdce05cf9c1c`, committer time
`2026-09-07T18:29:09Z`. Its workflow already contains Review fallback, Save honest
final result and the exact pr-review-result artifact. This predates actual
PR 812 run `34156734074`, created `2026-09-07T19:44:32Z`; the bridge deployment
time must not be substituted as a floor that drops this failure. A read-only
current API sample `34168264407` independently identified PR Review workflow
`352327391` and repository `1286600062`; these observations are not claimed
as initialization, full inventory or remote recovery acceptance.

## Reused boundaries

`DiscoveryRuntime(root, environment=None, api=None).run(limit=8, run_id=None,
attempt=None)` authenticates the existing current-main first-attempt controller
and shared short lock through Runtime. It replays only its separate journal,
using the actual Journal pending-append protocol. No Runtime.reconcile call or
scheduler journal write exists. Outbox operations only persist a verified queue
payload, not a business Issue/comment POST or delivery claim.

CLI: `--root --summary --limit [--run-id --attempt]`. There is no executable
output file, GITHUB_OUTPUT action or heavy-job bridge. The automatic entry owner
will invoke this from its independent report step. Report error must remain
visible without changing an already durably published scheduler execute action;
scheduler errors must not be swallowed by a combined try block.

## Inventory and receipt semantics

Each invocation collects at most one complete time window (normally up to one
day), stopping two minutes behind the supplied current time. Half-open UTC
windows map to inclusive API seconds with end minus one second. Full pages,
stable total count, distinct IDs, created-time bounds, actual repository numeric
ID and fixed review workflow/path/event are checked before the inventory is
committed. Initial inventory always retains attempt 1, not the API's latest.

Windows above 200 runs subdivide by time; this bounds each journal event below
its transport size limit and detects the API's filtered-result cap. A still
dense single second becomes an explicit inventory gap. Partial pages, 403/404,
inconsistent metadata or unknown API responses never mean empty inventory and
do not advance that interval. Gap repair remains explicit through independently
complete inventory evidence; no operator can erase it by claiming success.

Artifact age is not inventory absence. Read older windows normally: a retained
31-day-old run/receipt can still be consumed. Only an explicitly expired exact
artifact gives retention-lost; a missing artifact or API failure is unresolved.
The actual review consumer independently validates source/control, jobs, full
artifact and historical policy, including its genuine later-attempt rules.
Read-through receipt hashing records the consumer's complete read commitments;
the hashes themselves are not authentication. Valid review and closed mapper
receive their distinct terminal dispositions, not an invented outage report.

Failure payloads are frozen and durably queued in the existing Outbox before
recording failure-queued with its exact key. Verify the complete queued payload
after recovery. A response-loss between journals reuses that intent, never
duplicates the business POST. Queued is deliberately not delivered; independent
Outbox draining retains unknown-write/manual-reconciliation boundaries.

## Durable bounded metadata revisit

The necessary pure-protocol extension adds metadata-start and metadata-result
events, plus metadata_scan round/active/errors. Each round freezes the entire
known sorted run-ID set. The position persists across invocations; new runs join
the next round. Each successful generic run metadata observation independently
checks its original creation time and registers all discovered later attempts
before advancing. No dynamic modulo, restarting at the first ID or replacing
the original attempt is permitted.

An API error persists a separate unresolved metadata obligation and advances
the round position so siblings are not starved; the next frozen round revisits
it. It never downgrades an authenticated terminal review. Exact event replay
restores positions idempotently, including after lost journal responses.
An individual run above the explicit 64-attempt recovery bound remains an error,
not silently truncated. Budget counts run IDs (1..32), not API calls; each
attempt can require its complete authenticated receipt. Large or unavailable
history remains visibly incomplete rather than pretending a latency guarantee.

## Verification and limits

Pure tests exercise frozen membership, next-round newcomers, durable position,
metadata errors preserving terminal review, all later attempts before progress,
and strict identity/generation rejection. Bridge tests run actual Git config
reads, Runtime writer authentication, both Journals, collector and Outbox through
strict HTTP fixtures. The independently owned shared-manifest loader is injected
only at its constructor boundary to use isolated fixture Issue identities; its
own Task tests the real fixed 807/817 loader. No fixture proves actual hosted
permissions, lock attestation, API snapshot atomicity or a platform outage.

Run both targeted suites, full CI with pinned actionlint, staged ownership and
whitespace, and an actual precommit Portal check. Record failures honestly.
No test, coverage floor, timeout or owned suite is reduced.

Local verification: 21 bridge tests and 49 pure protocol tests pass; the full
CI contract discovery passes 1,609 tests with pinned actionlint, and staged
ownership passes 66 tests. The actual precommit Portal check exits 1: its first
57 tests contain 54 passes and three missing-dependency failures (`glob`,
`gray-matter`, `cheerio`); downstream Portal stages were not reached. This is
not a Portal pass or a product full-suite execution claim.

Early independent review identified an unjustified age-based inventory skip
and missing numeric repository identity validation. Both were corrected and
covered by retained 31-day evidence, HTTP-error and wrong-repository regressions.
Independent review reran all 21 bridge and 49 protocol tests. Final local
hardening also rejects a non-string metadata outcome status with why/remedy.
Remote discovery storage, real shared-loader integration, hosted inventory and
automatic activation remain separate prerequisites, not fixture acceptance.

## Version Management

Version impact: none — internal CI discovery state adds review-specific cursor
events; it allocates no Product/Assembly/Module/Host/Provider/Contract identity.
Old discovery event history replays with an initially empty metadata cursor.

## Documentation Impact

Documentation impact: none — internal bridge/protocol/tests and plan only;
Portal current testing/release pages remain separately owned T5 obligations.

Pitfall impact: none — early review corrections are covered by focused local
regressions; no new historical platform incident or release is asserted.
