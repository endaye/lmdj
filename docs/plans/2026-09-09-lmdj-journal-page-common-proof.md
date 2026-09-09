# Share common workflow and main proofs within one journal page

Status: source implemented and locally verified; remote acceptance outstanding.
Relates to #979 and #1048.

## Scope and evidence

Report-only run `34307067889/1` recorded 977 HTTP attempts in the entry process
and 542 in discovery, with respective elapsed times 327973 ms and 228315 ms.
No product jobs ran. This is one burst sample, not a representative capacity
baseline or a bill. Family counters do not attribute time to individual endpoints.

The journal currently shares four control-proof reads only for identical
controls on one page. Different controls still read the same workflow identity
and main ref separately. For N unchecked writers, K control identities and W
workflows, retain every run and complete job inventory and every control source
and ancestry proof, but share the validated workflow identity and exact main SHA
within this page. With one job page per writer the fixture cost becomes
`2N + 2K + W + 1`, instead of `2N + 4K`. The distinct-100-control, one-workflow
case must reproduce 600 GETs before the fix and 402 after it. The existing
100-writer/single-control case remains 204 GETs. Neither predicts live latency.

## Implementation Task

Declared files:

- `scripts/ci/batch_github_journal.py`
- `tests/build/ci_batch_github_journal_test.py`
- this plan
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md`

Keep the existing four-reader limit, page parsing, ordering and atomic publication
of authenticated writer identities. Extend the existing page-local single-flight
proof mechanism, not a process-wide API cache. Share only a validated main SHA
and successful workflow identity checks keyed by repository/path/ID; retain no
raw response dictionaries. Failures are shared only within the page and never
published as trust. All futures finish before a failed page exits.

Compare every distinct control against the same captured main SHA. A control
newer than that snapshot fails the page; do not silently retry against a newer
main for that writer. A subsequent page/attempt obtains fresh common proofs.
Standalone checkpoint/writer authentication keeps its existing fresh reads.
Do not change mutable comment metadata reads, journals, POST recovery, limits,
selection, triggers, permissions, deployment or version identity.

## Verification and remaining acceptance

Start with failing distinct-control request-count and shared-failure regressions.
Verify independent workflows, per-control source/ancestry rejection, same-page
main pinning, changed main/workflow on a subsequent page, and retry after a failed
page. Retain exact run/jobs, metadata, ordering, reopen and lost-POST journeys.
Run journal and runtime/report/discovery/controller tests, complete CI contract
discovery, staged ownership and Architecture Portal check before commit.

After merge, inspect actual counters and successful report delivery on the new
control. Source-shaped fixtures do not prove platform locking, quota savings,
backlog drain, end-to-end latency or the full result-driven delivery plan.

Local evidence: both new regressions failed before implementation (600 versus
402 GETs, and four versus one failed main request). All 63 journal tests and
2,168 complete CI contract tests then passed with no skipped tests. Portal check
passed 112 tests and the production build's 44 route/internal-link checks.
Independent agent inspection found no blocking issue in the four-file change.

## Version Management

Version impact: none

Reason: internal authenticated transport optimization; no Product, Host,
Module, Provider, Contract, Assembly or snapshot allocation.

## Documentation Impact

Documentation impact: none

Reason: internal page-local proof reuse changes no operator command, selection
policy, current Portal fact or public interface.
