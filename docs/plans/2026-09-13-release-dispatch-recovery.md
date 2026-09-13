# Read-only recovery of an uncertain release dispatch

Status: delivery integration of original `d2e8fe4b` onto reviewed evidence
consumer `3c998029` (PR #1290, pending merge at Task start). Its live-clock,
bounded ZIP decoding and passive Git protocol protections remain intact.
Original-stack verification below is historical, not current delivery proof.

## Scope

R4 must recognize the original workflow run after an uncertain POST without
blindly dispatching again. Extend the exact-run consumer with authenticated
actual-input reading and a complete workflow-run scan. Do not select by
run-name, newest success, or only one control SHA: a duplicate operation on
another control revision must also be observed and refused.

Declared files:

- `tools/release/dispatch_evidence.py`
- `tools/release/github_api.py`
- `tests/build/release_dispatch_evidence_test.py`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-dispatch-recovery.md`

The API reader adds only bounded workflow-runs GET routes. The exact-input
verifier remains strict. Actual-input reads still authenticate API numeric
identities, actor, first attempt, source ancestry, producer/upload, artifact
digest/retention and complete closed canonical receipt before exposing inputs.

Discovery requires the complete pre-POST run-ID snapshot from the trusted
operation journal. It must have been frozen before the sole POST intent;
a later scan or self-declared list cannot substitute. Original request IDs
must be unique and resumptions must reuse that journal, never allocate a new
operation with an old ID. This Task does not implement or authenticate that
journal lifecycle. Do not exclude older runs merely because their source is
before a minimum reviewed revision: source age is not proof of request age.

Scan all workflow run pages twice, validate repository/workflow identities,
and compare stable run identities while allowing effect status to progress.
Only prior IDs and authenticated different actor/event/ref rows are excluded.
Read every new candidate's authentic inputs; another request can be excluded
only after authentication. Any unreadable candidate prevents a uniqueness
claim. Multiple matching operation IDs, changed exact inputs or a different
control revision return conflict. Zero matches, incomplete/changed inventories
or unavailable evidence return unknown, never absent. A single unique match
is reverified and returns correlated, not effect success or retry permission.
This observation is not a global lock against a later external duplicate.

## Verification

Extend the existing registered consumer suite using real temporary Git,
producer receipts and the actual closed HTTP transport. Exercise single
match, zero matches, duplicate runs (including another control SHA), an
authenticated unrelated request, unreadable candidates, exact pre-POST ID
exclusion, mid-read arrivals and truncation. Preserve original exact-input
rejection and all prior identity/protocol/ZIP regressions. Run the CTest
consumer/producer/Portal-consumer contracts, API regressions, staged ownership
and Portal check. No actual dispatch or deployment.

Remaining integration: durable authenticated pre-POST baseline/intent storage,
one-POST controller and restart proof, production backend/CLI/service wiring,
and the separate publication/deployment far-side verifiers. These remain
required for complete release automation; this scan alone does not implement
an unattended release or safe replay of a timed-out write.

## Version Management

Version impact: none

Reason: read-only internal correlation discovery; no Product/Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: document discovery results and the trusted pre-POST baseline boundary.

## Current delivery verification

All original behavior and the prerequisite's four live-clock/ZIP regressions
remain present. Consumer/discovery 34/34 (8.578s), producer 12/12 (0.265s),
existing Portal evidence consumer 22/22 (9.772s), and GitHub API 39/39 (0.013s)
passed, exit 0. An independent complete five-file review found no actionable
finding and independently reran consumer 34/34 (8.503s).

`scripts/core.sh configure dev` exited 0 with Python 3.14.7. The three
registered consumer/producer/Portal evidence CTest contracts passed in 18.02s
with unchanged timeouts. Staged ownership/admission passed 74/74 (5.500s);
output: `/tmp/lmdj-dispatch-recovery-delivery-scope-v1.log`.

With locked dependencies and Node 22.22.2, `scripts/docs-site.sh check`
exited 0: 144/144 tests, 10 diagram sources / 20 outputs, snapshot validation,
typecheck, changelog projection checks, optimized build and 47 routes/internal
links. Output: `/tmp/lmdj-dispatch-recovery-delivery-docs-v1.log`.

These checks use the real producer/consumer/Git entrypoints with deterministic
API fixtures. They do not establish real pre-POST durable capture, live
dispatch recovery, effect success, or full unattended release acceptance.
Pitfall disposition: no separate entry; the causal regressions capture the
behavior and the journal trust premise remains explicit.

## Historical original-stack verification record

Consumer/discovery suite 30/30 passed; existing producer 12/12, API 39/39 and
Portal consumer 16/16 independently rerun by the reviewer, all exit 0. Complete
five-file independent review found no actionable finding. Local CMake
configuration exited 0 and all three selected CTest contracts passed;
staged ownership 74/74 and whitespace checks passed. Logs:
`/tmp/lmdj-dispatch-recovery-{tests-v1,configure,ctest,api,scope}.log`.

No GitHub write or live dispatch was made. The pre-POST baseline in the tests
is an explicit fixture premise, not real durable-clock/authorization evidence.
The default empty test baseline means no earlier runs existed in that fixture;
production callers must never replace missing journal state with an empty list.
Pitfall disposition: no separate entry; the regression tests capture unknown,
duplicate, cross-control and incomplete-scan behavior. The unimplemented
journal lifecycle remains an explicit implementation and acceptance gap.

Portal check exited 0: 139 tests and 47 routes/internal links passed; raw
log `/tmp/lmdj-dispatch-recovery-docs.log`. A live read of prerequisite PR
#1266 still showed OPEN/unmerged at head `c8fab3b67b6abe3bff708b5563acfc84b0e9e671`;
no owner adoption, push or merge is inferred from this local verification.
