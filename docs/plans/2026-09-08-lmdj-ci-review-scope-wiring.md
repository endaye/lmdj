# T2b — Serial backend execution and trusted publisher wiring

Depends on T2a's strict review/fallback protocol and T1 scope records. Does not
modify product test triggers, self-test reporter, merge protection or releases.

## Declared files

- `.github/workflows/pr-review.yml`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_scope_codec.py`
- `tests/build/ci_review_scope_codec_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `.github/scripts/advisory_review_liveness.py`
- `tests/build/ci_advisory_review_liveness_test.py`
- This plan.

## Implementation

Reuse the pinned Claude action for GLM then Kimi and the pinned existing Grok
CLI invocation after both fail. Every attempted result goes through T2a. A
valid review with findings stops fallback. Each backend has a five-minute step
limit; Grok also has a subprocess timeout. The model job retains read-only
permissions; only the separate publisher has existing PR write/actions read.
No repository variables or remote permissions are modified.

Retain full original `review.json`, including `test_scope.reason`, plus sanitized
history/context/result and all-failure artifact. The publisher authenticates
the actual run attempt, source workflow bytes, main control ancestry and current
PR head, and recomputes actual Git paths plus T1/T2a output before writing.
An immutable COMMENT record supplements the 30-day scope artifact. Same-head
authenticated prior records are unioned; different control/policy evidence
fails closed for explicit reconciliation rather than silently shrinking scope.

Publication uses the existing guarded COMMENT writer. Scope labels are added,
never replaced destructively; accumulated historical labels are explicitly not
selection authority. Downstream reads the authenticated current-head record.
Exact same-run/attempt record replay detects an existing review before posting;
an ambiguous write outcome is not automatically retried in the same process.

Trusted scope metadata uses a versioned zlib/base64 codec with a 1 MB raw bound,
40 KB encoded marker bound and 60 KB overall COMMENT budget. Duplicate keys,
trailing streams/bytes, truncation and decompression overflow are refused. Model
summary retains its original independent 12,000-character validator. Metadata
overflow does not discard a valid review: it emits an authenticated unavailable
marker requiring full scope, retained across later same-head publication. The
original structured model artifact is preserved. Failed input collection gates
every subsequent backend step; no model is called with a missing diff.

All-backend failure remains not-reviewed and makes the publisher fail visibly.
The model job's successful result upload means it produced a receipt, not that
a backend reviewed successfully. Existing issue-capable reporting is wired by
T4; this Task neither opens issues nor grants issue write permissions.

## Verification

Lowest tier: pipeline adapter tests with real temporary artifact files, T2a/T1
contracts, updated standalone workflow contracts and pinned actionlint 1.7.12.
Stage new files before `ci_change_scope_test.py`; inspect cached diff/check.
Legacy Grok/Claude Core CI contracts remain unchanged and must still pass.

Mocked subprocess/API results do not prove service credentials, installation
permissions, timeout cancellation behavior, platform head races or write
visibility. O1 must exercise GLM failure → Kimi success, full three-backend
failure/reporting, exact-head immutable record/labels and replay. Oversized
complete diffs, unavailable Git/API history or mismatched policy remain explicit
review failures needing takeover, never truncated/clean evidence.

Pitfall impact: none; known API identity, source provenance and bounded-write
rules applied. No test strictness, owned lane or product timeout was reduced.

## Documentation Impact

Documentation impact: none

Reason: Review-internal wiring only; product test trigger/governance Portal
cutover remains T5, no manifest or Product Assembly changes.

## Version Management

Version impact: none

Reason: CI-internal records and review workflow only; no Product Build, tag,
publication, deployment or Channel promotion.
