# R3: durable evidence PR create and guarded merge effects

Status: delivery in progress on main `b91c5e4b` (merged workspace PR #1277),
replaying `c42d0e3a`.
Not pushed, merged or activated in a production controller. Original-stack
results below are historical, not delivery evidence. Current baseline: 23/23
tests pass. Delivery is checking durable state-size and trust-boundary gaps.

Delivery red cases reproduced oversized state replacing a readable journal,
missing state after unknown POST allowing a second POST, and callback-raised
EvidencePrError leaking arbitrary text. Save now enforces the reader's 64 KiB
encoded-byte bound before opening a temporary file. A durable private enrollment
marker distinguishes state loss from first use; initial state is saved before
authority observation, so a failed initial authorization can resume. Missing
state/marker or interrupted enrollment fails closed for explicit reconciliation,
not another POST. It does not detect deletion of the entire journal; authenticated
outer request enrollment and durable service storage remain required.
API/authority/review/merged-verifier exceptions are sanitized at their callback
boundaries, regardless of exception type; module-owned invariant diagnostics stay
specific. Current suite passes 31/31; independent full six-file review and 31/31
rerun found no remaining actionable finding. The reviewer also used a real fork
after marker fsync but before initial state save: reopening refused with zero API
calls, preserving the explicit reconciliation boundary. API 39/39, journal 21/21,
driver 13/13 and staged ownership 74/74 pass. Clean Node 22.22.2 npm install
retains the existing 27 advisories (9 moderate, 18 high), no dependency changes.
The enrollment fork proof is now a permanent regression: final suite and
independent rerun pass 32/32. CMake config and registered CTest pass (1/1,
Python 3.14.7); full Portal check passes 144/144 tests, production build and
47 routes/internal links. All delivery verification commands above exit 0.
No production remote
mutation was used in these fixtures; delivery command returns are retained in the
agent execution transcript rather than the original-stack log paths below.

## Scope

Implement internal evidence PR create/reconcile/guarded-squash/verify sequencing
with a closed production GitHub transport. Bind operation/request identity,
repository and actor numeric IDs, base/head/tree, exact tag/target and Task
verification digest. Generate a fixed declaration-bearing body with no model
text, closing directive, credential or user-selected destination. Only the
operation-bound branch in endaye/lmdj targeting main is admitted.
The generated PR declares the three required Task commands; authority must
resolve its Task evidence digest and confirm actual exit 0 before creation.

Persist private canonical intent before POST or PUT under the existing exclusive
writer lock. ACKs do not complete transitions. Discover the single exact PR using
bounded all-state inventory, then numeric-ID reads; authenticate full body,
author, repositories, branch/head and state. Empty observations after an attempted
write remain unknown and never trigger another write. Recovery may adopt a late
positive matching effect; merge PUT always uses expected SHA and squash, with
no auto-merge, admin override, branch/protection mutation or other REST write.

Trusted caller gates remain mandatory: original release/Task authority and
source/protection preconditions, exact-head review eligibility PLUS all findings,
conversations and closing relations, then actual squash/source verification.
The latter two return typed Observation evidence, never a boolean. Review proof
is saved with the merge intent and passed to merged-source verification on
resume; an externally preexisting merge instead requires independently verified
historical review. Unknown mergeability yields before recording merge intent.
The REST contract is documented at
https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request.
The gate implementations are
not implemented by callback injection or PR body hashes: a production backend
must compose the actual repository verifiers before activation. Remote branch
push, public run/status/resume intake and durable service integration remain
unfinished. This Task implements real transport/effect sequencing but does not
enable unattended publication or exercise production mutations.

Declared files:

- `tools/release/evidence_pr.py`
- `tools/release/github_api.py`
- `tests/build/release_evidence_pr_test.py`
- `CMakeLists.txt`
- `apps/docs-site/docs/operations/version-and-release.mdx`
- `docs/plans/2026-09-13-release-evidence-pr.md`

## Verification

Production GitHub transport with fixture responses covers create → pending
review → guarded merge → far-side/source verification → reopen/reverify.
Assert identity drift, missing gate evidence, review change and protection drift
cannot authorize writes. A timeout before either effect cannot trigger retries;
a late positive effect is adopted. Actual process exit immediately after POST
or PUT retains a far-side fixture record and durable local intent; a new process
context adopts the original PR/merge without duplicate writes. This is not real
GitHub review/protection enforcement or live merged-source proof: those gate
callbacks are explicit fixtures here. Run existing API/journal regressions,
staged ownership, full Portal check and independent read-only review.

No process-only pitfall is claimed: these are newly implemented invariants with
direct regressions. No existing threshold, test strictness or gate is reduced.
### Original-stack verification history

Historical live read-only check found PR #1266 still open at
`c8fab3b67b6abe3bff708b5563acfc84b0e9e671`, with no merge commit; this local stack
does not manufacture its unresolved owner adoption.

Final results (all exit 0): PR transport/state/recovery 23/23, existing GitHub
API 39/39, request journal 19/19, sequential driver 13/13, staged ownership
74/74 and Python compilation. Full Portal check passed 139/139 tests and the
production build's 47 routes/internal links. Raw logs:
`/tmp/lmdj-evidence-pr-tests-final.log`, `/tmp/lmdj-evidence-pr-api.log`,
`/tmp/lmdj-evidence-pr-journal.log`, `/tmp/lmdj-evidence-pr-driver.log`,
`/tmp/lmdj-evidence-pr-scope.log`, `/tmp/lmdj-evidence-pr-docs.log`.
Independent reviewer `/root/release_journal_review` inspected all six files,
rechecked retained review/body changes and independently ran all 23 PR tests;
no actionable finding remained. No production PR, Release or deployment was
created during verification. Existing locked dependency advisories remain
outside this Task; no automatic dependency repair was applied.

## Current-head review follow-up

Run `34757633088/1` successfully published review `5190686665` for head
`9837605e4d8456dcbf94a866a0fa9d6fb8ca8709`; original publisher failure
`34744833430/1` remains unexplained and retained, not reclassified as passing.

The inventory-amplification finding reproduced: 100 distinct rows caused 100
detail reads before the already-required multiple-PR rejection. Rejecting the
second distinct identity immediately preserves that invariant and limits detail
reads to one per discovery. Duplicate identity refusal remains unchanged.

The stale-mergeability finding does not establish an unsafe merge: the observation
is only a precondition, not a transaction lock. GitHub enforces conflict/protection
and exact-head constraints on PUT, and this controller verifies the actual merged
source afterward. Repeated identical GETs cannot remove the race. A new real
transport-fixture HTTP 409 regression confirms stale `mergeable=true` followed
by server refusal stays `unknown-merge`, preserves the PR unmerged, and reopening
never repeats PUT. It uses the same expected SHA and squash payload; it does not
prove live GitHub semantics or grant retry permission.

## Version Management

Version impact: none

Reason: internal release-control tooling; no Product Build, Assembly, Module,
Provider or public Contract change and no snapshot rewrite.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

Reason: distinguish PR effect implementation from authenticated production gates.
