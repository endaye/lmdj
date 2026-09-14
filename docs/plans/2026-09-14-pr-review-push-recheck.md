# Automatic repair recheck on PR push

Issue: #1322. Date: 2026-09-14.

## Task and declared files

One Task extends the existing collector, model and publisher to recheck a
bounded list of unresolved authentic bot findings during the ordinary
`pull_request.synchronize` review. It does not launch another workflow or a
model call per finding. Keep the explicit dispatch single-comment contract.
Do not interpret prose replies or add comment commands in this Task.

Declared files:

- `.github/workflows/pr-review.yml`
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_recheck.py`
- `scripts/ci/review_pipeline.py`
- `tests/build/ci_review_recheck_test.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_review_pipeline_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/plans/2026-09-14-pr-review-push-recheck.md`

## Behavior

Collect the complete paginated thread inventory. Ignore resolved and human
threads; select original bot roots in stable comment-ID order. Attempt at most
four candidate authentications per run and admit at most 1 MiB of combined
repair context, preserving the existing per-request bound. Report deferred,
unchanged, unavailable and rejected candidates explicitly; none is resolved or
counted as verified. No silent truncation and no increase to provider budgets,
output caps, timeouts or permissions. This bounded first version may require the
existing manual entry for overflow or unavailable historical evidence.

Use a shared read cache only within one collection/publication observation to
avoid repeated download of the same original review artifact. Head and thread
boundary reads always remain fresh. Authenticate each original against retained
artifacts, original source and ancestry. An unchanged finding file has no
source-change proof under the existing contract: report it as not rechecked,
never assume that the finding is fixed. Cross-file runtime proofs, removed
paths and rewritten history retain the manual fallback.

Add an optional `repair_requests` input list, mutually exclusive with the
existing singular field, and `repair_rechecks` native verdict list. Require
exact one-to-one IDs with no omissions/duplicates/unsolicited verdicts. Every
request must reach the real prompt; every resolved verdict retains all current
causal quote and source anchor checks, including no new ordinary findings.

On synchronize, the existing per-PR concurrency replaces superseded work and
all existing head checks apply. The workflow has one model step. Empty batch
input requires no extra model fields/calls. The publisher authenticates the
batch/native mapping, then publishes each thread sequentially using existing
receipt reconciliation and compensated head/conversation race handling.
Refusals keep the affected thread open and visible. Successful earlier thread
receipts survive a later refusal; retry must reconcile them without duplicate
replies. GitHub has no atomic head-CAS thread mutation; no merge authority is
inferred from automatic resolution.

## Verification

Lowest-tier tests exercise actual collection and publication with strict API
seams and authentic retained review artifacts. Cover mixed bot/human/resolved
inventory, pagination, per-run bound/deferment, unknown provenance, unchanged
source, no-candidate ordinary review, exact verdict inventory, missing prompt
context, source mismatches, concurrent head/conversation changes, retry after
partial publication and no duplicate writes. Use the real pinned PRReviewer /
LiteLLM handler with only completion transport replaced to carry two requests
through one model call, parsed YAML, publisher and separate far-side states.
Pipeline tests exercise the actual synchronize entry and reject forged mode.

Run adapter (including pinned integration), recheck, pipeline (including T2),
input, review-wait, scope and workflow suites. Run actionlint with ShellCheck,
`scripts/docs-site.sh check`, staged new-file ownership and final scope plan.
No new required merge check. Tests preserve previous refusal cases and budgets.

Live journey after source review/merge and immutable installed adapter overlay:
create an isolated unmerged acceptance PR; obtain an authentic bot finding;
push a source repair; observe synchronize input -> one ordinary model review
with repair verdict -> evidence reply -> bot-resolved thread at exact head.
Retain real run/artifact/head/installation identities and limitations. Never
merge an intentional test defect. Local fixtures do not establish platform or
installed engine acceptance; keep the Issue open until the live journey passes.

## Version Management

Version impact: none — internal CI tooling changes no Product Build, module,
Provider or public Contract identity. Install adapter through the supported
immutable overlay installer, preserving previous release and shared ledger;
no dependency, credential, model or budget changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: push now initiates bounded source repair verification automatically;
document deferred/unavailable cases and the existing manual fallback.
