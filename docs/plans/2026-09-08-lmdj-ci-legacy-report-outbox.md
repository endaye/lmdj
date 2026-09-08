# Legacy full reports through the incremental outbox

## Task and declared files

One local prerequisite Task, based on main
`dc1e57622136b019aab1a514298ff252a0c32ae6`. This is not T5 trigger activation.

- `scripts/ci/self_test_report.py`
- `scripts/ci/report_runtime.py`
- `tests/build/ci_self_test_report_test.py`
- `tests/build/ci_report_runtime_test.py`
- This plan.

The existing workflow and all release candidate consumers remain untouched.
No permission, Product identity, fixed Issue, epoch or scheduler state changes.

## Interface and invariants

`self_test_report.plan_run(api, run_id, attempt=..., repository=..., sleep=...)`
returns `(RunReport, tuple[Report, ...])` without performing Issue writes.
An explicit positive run/attempt must match the actual latest API observation;
a newer rerun cannot silently replace the requested attempt. Reporting an
explicit actual second attempt remains compatible with the legacy reporter;
this is not first-attempt candidate eligibility or a release approval.

The shared internal planner retains the previous source workflow, main ancestry,
deployed producer boundary, exact target/control/run/attempt, frozen control
policy, full-suite verdict and digest validation. It also preserves verified
skip and incomplete-evidence diagnostics. The new path does not reinterpret
workflow green as a verdict, shrink the inventory, execute tested source or
translate incremental artifacts into legacy evidence. The full fixture uses
the actual 16-suite policy and aggregate, not a 14-lane release fallback.

`report_runtime.py --config CONFIG --root ROOT --summary SUMMARY legacy
--run-id RUN --attempt ATTEMPT [--limit 8]` authenticates its existing writer
and calls the planner, then the existing outbox. Read errors fail before queue;
not-applicable sources produce no delivery. Every planned payload is frozen
before business writes. The established queue/claim/ack/delivered protocol owns
POSTs and exact receipt verification; scheduler progress is not changed.
Previously queued payloads can use `drain` after source artifact expiry.

## Required T5 atomic follow-up

The old `self_test_report.py report` and `missing` CLI paths, `report_run`,
`reconcile_recent` and `check_missing` retain their current behavior in this
prerequisite because main still invokes them. They are not outbox-safe simply
because a new API exists. T5 must remove the old workflow invocations and
disable their direct-write entry points together, with explicit why/remedy
directing operators to the configured outbox command. In particular, retire
daily missing-batch writes rather than sending obsolete daily alerts through
the new outbox. Preserve the low-level reporting adapter used by the outbox
and its unknown-write/receipt tests; do not delete those tests to stop an entry.

T5 owns automatic Core CI completion routing, bounded legacy recovery scans,
review completion routing, main wakeups and the independent health schedule.
This Task adds no dispatcher, schedule, API write credential or remote action.
All shipping remains HOLD until root's applicable acceptance boundary.

## Verification

The new complete-legacy-to-outbox journey first fails on the absent `legacy`
operation, then passes after the adapter is installed. Existing 72 legacy
report tests remain intact. New tests cover actual 16-suite manual candidate
planning without writes, a missing required suite, exact attempt mismatch,
explicit second-attempt identity and incomplete-result planning.

The far-side runtime journey checks real temporary-Git writer authentication
and HTTP-shaped Issue Journal transport, persisted queue/claim/ack/delivered,
exact business body and receipt, replay without another POST, unchanged
scheduler storage, API failure before queue, CLI input propagation and drain
after artifact removal. A legacy POST that actually creates its Issue and then
loses its response leaves a durable claim; replay recovers the exact receipt
without a second POST. Evidence endpoints and business APIs remain fixtures:
this does not establish real token scopes, hosted concurrency, eventual
visibility or successful full-candidate O1 evidence.

Run the complete self-test reporter, report-runtime, outbox and workflow
contracts, then all CI contracts and staged ownership. Run the Portal check
because documented source tooling is refactored; record any unavailable local
dependencies as failures, not a pass. No coverage floor, suite, retry bound or
acceptance leg is removed. Existing fake-tool-stub-strictness escalation #726
remains open; code-expressed planner invariants receive tests, not a fabricated
process recurrence.

Local results: 77 self-test reporter and 43 report-runtime tests pass. Final
complete CI discovery passes all 1,436 tests without skips, including the
lost-response regression. All 66 staged ownership tests and the staged
whitespace check pass over the exact five declared files.
Portal check reports 54 passes and three failures because glob, gray-matter
and cheerio are unavailable locally; no checks were skipped and this is not
a Portal pass. The complete CI run uses pinned actionlint 1.7.12.

## Version Management

Version impact: none — internal inactive report composition, no Product,
Module, Contract, Host, Provider, Assembly or intent identity changes.

## Documentation Impact

Documentation impact: none — existing automatic behavior remains unchanged;
this prerequisite adds an unconnected manual CLI adapter. T5 must update
current operational pages and governance with its actual trigger cutover.
