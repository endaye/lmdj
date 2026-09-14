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

## Review follow-up: distinguish byte-bound deferment

The independent review of `fc7cc28b` identified that combined byte overflow
was reported as an evidence refusal. Report it as `deferred` with the manual
remedy. The authentication-attempt limit remains four, including candidates
that cannot be admitted; do not silently raise API work to fill four slots.
Declared files: this plan, `scripts/ci/review_recheck.py`, and
`tests/build/ci_review_recheck_test.py`. The focused regression first observes
`not_rechecked` for two individually valid 600 kB contexts, then requires one
collected request and a deferred second candidate. Run the recheck suite.
Version impact: none. Documentation impact: none — restores the already
specified overflow behavior; no portal contract changes.

## Live follow-up: current repair source line map

Automatic synchronize run 34842846546 collected both authentic findings but
rejected the model output because current_quote did not match the supplied
current line span. The original line-10 finding had left the net PR diff after
repair; only PR-added lines 12–22 had explicit numbers in the prompt. The
failed result does not retain the native text, so it cannot identify whether
the mismatch was quote encoding or line counting. Preserve this limitation.

Provide an explicit line/text map for every current repair file, once per
path, including lines outside the overall PR RIGHT inventory. Require this
whole derived block in coverage and direct the model to copy text separately
from line numbers. Keep exact quote/anchor validation unchanged. This improves
the evidence supplied; it does not certify arbitrary model outputs.

Declared files: this plan, `scripts/ci/pr_agent_review.py`,
`tests/build/ci_review_recheck_test.py`, `tests/build/ci_pr_agent_review_test.py`.
Focused tests prove an outside-diff context line has an exact source mapping,
missing mapping makes prompt coverage incomplete, and the real handler reply
uses the actually supplied map through YAML parsing and both resolved states.
Run recheck and pinned adapter suites, review/merge, install a new immutable
adapter overlay and repeat a real synchronize event on the unmerged acceptance
PR. No token, time, monetary, permission or source-proof threshold changes.
Version impact: none. Documentation impact: none — restores the documented
exact-source verification boundary; no new portal-facing behavior.
