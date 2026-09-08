# Coalesce PR Review wakeups

## Scope

The Owner authorized commit, push, PR and merge for CI cost remediation while
retaining paid macOS availability recovery. This independent Task removes the
PR Review completion subscription from Self-test Report. Main pushes continue
to coalesce new targets in the durable scheduler. Actual batch completion relay
and legacy Core CI completion remain subscribed, without changing authentication,
scope union, event receipts or writer cancellation behavior.

Declared files:

- `.github/workflows/self-test-report.yml`
- `tests/build/ci_incremental_cutover_workflow_test.py`
- `tests/build/ci_batch_runtime_workflow_test.py`
- `tests/build/ci_o1_claim_probe_workflow_test.py`
- `tests/build/ci_o1_probe_workflow_test.py`
- `scripts/ci/review_discovery_runtime.py`
- `tests/build/ci_review_discovery_runtime_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- this plan

The parallel routing Task moves routine control to Contabo; this Task does not
alter runner labels and can merge in either order without granting hosted
exceptions. Do not infer a complete cost migration from this wakeup/recovery diff.

## Behavior and tradeoff

PR-only opened/synchronize/review activity no longer creates a scheduler/relay
chain. Reviews still publish authenticated scope and findings. Existing bounded
discovery on idle main/15-minute health observations recovers retained valid
reviews, closed mappings and failure reports. This can delay review-infrastructure
Issue creation: the health interval is not a delivery SLA when the control pool
is down, busy executing a batch, or processing backlog. Unknown scope still
selects the deterministic safe fallback; labels never reduce required coverage.

Keep the old authenticated review callback handler and exact manual
report-review/report-discovery recovery for old queued runs and retained data.
Keep immediate completion relay: the GitHub event does not expose whether its
parent actually ran product jobs before allocating a runner. Removing that
relay without another verified completion signal could strand or delay the
next batch. Eliminating all idle completion relays remains a separate design
item, not a claimed result of this Task. Do not cancel a writer or erase debt
to reduce event counts. The existing health tick is recovery, not daily testing.

## Verification

Run `ci_incremental_cutover_workflow_test.py`, full `ci_*_test.py` discovery,
`ci_review_discovery_runtime_test.py` (covered by discovery), actionlint and
staged ownership validation. Existing behavioral tests execute the actual
discovery condition for main, schedule, executing, failed and callback states;
new assertions retain bounded discovery and exact manual recovery. Exercise
post-merge PR Review completion without a new main push and observe no directly
subscribed scheduler run; do not confuse contemporaneous main/schedule or old
workflow callbacks with this event. Successful main-trigger execution and
subsequent discovery are separate far-side acceptance legs.

## Version Management

Version impact: none
Reason: workflow wakeups and discovery recovery change, without product or Contract identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof/
Reason: automatic review wakeups and the bounded recovery service policy change.

## Review remediation design

Keep the complete historical metadata scan and its existing budget. Each
invocation additionally services at most one pending/unresolved/retention-lost
attempt, selected by its oldest registration or disposition generation. Existing
authenticated journal events supply that order; no new state schema or service
is introduced. A still-unresolved visit persists its unchanged closed disposition
once, rotating behind existing obligations instead of starving siblings. New
registrations join at their actual generation rather than jumping ahead forever.
Historical scanning continues to discover reruns of previously resolved IDs.
Skip duplicate work when the normal scan already serviced the selected attempt.

The opportunity bound depends on the number of unresolved obligations ahead,
not all historical successful reviews. It is not a wall-clock delivery SLA:
storage/API outages, inventory gaps, expired evidence and load above capacity
remain visible failures. One extra exact-source attempt per invocation may add
API work; no timeout, authentication or runner routing is weakened. If append
fails, stop and recover the same durable journal; do not advance an ephemeral
cursor or retry a business POST.

For N historical IDs and A already registered live obligations ahead of a newly
registered attempt, the additional slot reaches that attempt within A+1
successful discovery invocations, independent of N. Later registrations have
larger generations and cannot jump ahead; permanent errors rotate behind it.
Enumeration still commits one complete bounded window per invocation; if W
readable windows include the new run's window, registration takes at most W invocations,
then the A+1 service bound applies. The selected run's generic metadata is read
directly to register later attempts, followed by its exact-attempt collector;
neither step waits for the historical scan position. Unreadable inventory/API or
failed journal persistence invalidates a time bound, never evidence strictness.
An unobserved rerun of an old already-terminal ID still requires the retained
complete historical scan (N-dependent); this Task does not promise a universal
artifact-retention SLA or eliminate that existing limitation.

The extra work is at most one generic run GET plus one exact collector attempt,
and at most one unchanged-disposition rotation when still unresolved. Normal
collector queue/disposition writes remain unchanged. Rotation stores one small
existing closed event, not another full state/inventory snapshot. In-memory
priority reconstruction adds one traversal of already authenticated events;
there is no new full-history API read just to choose priority. Journal append
retains its normal full-pagination/anchor verification cost, so persistent
unresolved load still grows the journal and needs operational monitoring.

Local red/green backlog→new failure→outbox queue→ordinary drain and replay,
unresolved rotation, live-run rotation and retained historical scan tests are
required. Local verification results are recorded below.
The page already lists the workflow and discovery runtime in source_paths;
existing source diagrams describe product modules, not controller scheduling,
so no unrelated diagram is changed.

## Review remediation verification

The actual old-terminal-backlog/new-failure journey first failed with `pending`
instead of `failure-queued`, then passed through ordinary outbox drain and
idempotent replay. The final 1814-test CI contract run passed without skips;
discovery runtime 29 tests passed, including exact later-attempt registration,
stable ordering ahead of newer registrations and actual attempt-2 reads.
Explicit actionlint 1.7.12 + ShellCheck 0.9 passed with only the existing
`queue` syntax compatibility exception. Ownership 66 and dirty diff-check pass.
`scripts/docs-site.sh install` used existing locked dependencies without lock or
package edits. Complete docs-site check passed: 81 tests, 10 source diagrams,
20 outputs, production build and all 42 routes/internal links. Logs are
`/tmp/lmdj-964-remediation-full.log`, `/tmp/lmdj-964-remediation-runtime.log`,
`/tmp/lmdj-964-docs-check.log`, `/tmp/lmdj-964-ownership.log`.
These are local fixtures and builds, not remote trigger/delivery acceptance.

## Pitfall Impact

Pitfall impact: none — this callback inventory regression directly states the
behavior, while the routing Task owns the billed-control allowlist pitfall.

## Release Impact

Release impact: none
Reason: no budget change, product test request, tag, release or deployment.
