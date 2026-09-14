# Explicit PR-Agent repair re-verification

Issue: #1305. Date: 2026-09-14.

## Task

Add one optional `recheck_comment_id` workflow_dispatch input to PR Review.
An empty input preserves ordinary review. One numeric ID selects one original
LMDJ bot finding. Reuse the existing read-only PRReviewer, complete-input
collector, cost ledger and separate write-capable publisher. Do not turn on
upstream's author-confirmation-based thread resolution.

Authenticate the original finding against its retained review artifact, collect
the complete thread, original file bytes and original-head-to-current-head diff,
and bind these to the current input digest. Review all ordinary PR input as
before, with one additional explicit source-verification verdict. Resolution
requires a causal explanation, exact original/current source quotes, and a
current quote intersecting an actual added line of the intervening fix. Only
source-provable repairs qualify; claims requiring tests, runtime or external
state without execution evidence are `insufficient_evidence`. Author replies
remain untrusted context. Deletions/renames or missing original artifacts which
cannot satisfy this conservative contract require manual review.

The publisher rechecks the original provenance, full conversation, original
source/diff and current head. Validate the native verdict and captured mapping
again; a missing verdict from an older installed adapter cannot resolve. Reply
with verdict/evidence and a request-specific idempotency marker, then resolve
only the selected bot thread. Read the far side after mutation. On a detected
head/conversation race reopen and report failure. GitHub has no head-CAS thread
mutation: this is a best-effort compensated operation, never merge authority.

Declared files:

- `.github/scripts/pr_review_target.py`
- `.github/workflows/pr-review.yml`
- `scripts/ci/pr_agent_review.py`
- `scripts/ci/review_pipeline.py`
- `scripts/ci/review_wait.py`
- `scripts/ci/review_recheck.py`
- `tests/build/ci_pr_agent_review_test.py`
- `tests/build/ci_review_recheck_test.py`
- `tests/build/ci_pr_review_workflow_test.py`
- `apps/docs-site/docs/operations/testing-and-proof.mdx`
- `docs/quality/2026-09-10-pr-agent-netcup-operations.md`
- `docs/plans/2026-09-14-pr-review-recheck.md`

## Verification

Run new focused recheck tests covering collection, actual typed verdicts,
publication, retries and compensated races. Run the pinned PRReviewer/LiteLLM
handler integration test with only the real completion seam replaced and no
network. Verify recheck context at that seam and the consumer verdict. Run
existing adapter, input, pipeline, review-wait, workflow and scope ownership
tests. Run `scripts/docs-site.sh check`. Run actionlint with ShellCheck available. No new required merge gate.

Journey: authenticated original finding -> fixed-head collection -> complete
model prompt -> explicit typed verdict -> fresh publication validation ->
idempotent reply -> selected thread resolution -> far-side state check. Record
each boundary's evidence. Negative cases preserve an open thread; uncertain
mutation requires fresh reads before any retry. Source fixtures do not certify
installed engine activation or real GitHub mutation. Preserve these acceptance
distinctions in the shipping report.

## Version Management

Version impact: none. CI tooling changes no product/module/contract identities.

Documentation impact: required. Document the optional repair recheck and its
installed-engine boundary beside the current PR-Agent production route.
Affected portal pages: /operations/testing-and-proof

## Deployment

The existing immutable bundle installer supports adapter overlays. After
source review, an updated adapter must be installed as a new root-owned
release; retain the previous release and shared ledger. No dependency, model,
budget, credential or host inventory expansion. Before activation verify the
candidate as the runner account and the exact installed adapter identity.
Do not claim live rechecks from local tests or activate by copying unverified
files over `current`.

## Live acceptance follow-up: historical run identity

Real recheck run 34826375573 exposed mutable GitHub run association metadata:
after a fix push, `pull_requests[].head.sha` on the original run becomes the
current PR head. Authenticate the original revision using the run's own
`head_sha` and retained artifact, while still binding the associated PR number.
Current-head checks and all artifact/workflow provenance remain required.

Declared files for this follow-up Task: `scripts/ci/review_failure_report.py`,
`tests/build/ci_review_recheck_test.py`, and this plan. Add one regression that
changes only the associated head and carries historical collection through
resolved far-side publication. Run recheck, failure-report and review-wait
suites; retain rejection tests for wrong run head and wrong PR association.

Version impact: none. Internal CI authentication only.
Documentation impact: none. This restores the already documented behavior;
no Architecture Portal route or documented contract changes.

## Live acceptance follow-up: source quote encoding

Run 34827038614 authenticated the historical finding and reached the model,
but its source quote failed exact original-line validation. Clarify source
quote formatting in the prompt: JSON-compatible double-quoted YAML preserves
leading indentation and avoids implicit final newlines. Keep exact source and
anchor validation unchanged. The old seam returned JSON, so update it to carry
the quote example actually sent to the handler back as YAML through parsing,
validation and far-side resolution.

Declared files: `scripts/ci/pr_agent_review.py`,
`tests/build/ci_pr_agent_review_test.py`, and this plan. Run the pinned adapter
suite including the real handler child and recheck tests. Review source, install
a new immutable adapter overlay, then repeat the live recheck before acceptance.

Version impact: none. Internal prompt formatting only.
Documentation impact: none. The documented exact-evidence contract is unchanged.

## Live acceptance follow-up: control revision refresh

Run 34827872529 produced a valid source-proven resolved verdict, but normal
review publication refused to combine a prior same-head scope recorded under
an older main control. Authenticate its provenance and target, retain that
historical record, and use the existing incomplete/full-scope fallback when
control revisions differ. Never merge advice across policies or narrow testing;
wrong targets and same-control invalid records still fail closed.

Declared files: `scripts/ci/review_pipeline.py`,
`tests/build/ci_review_pipeline_test.py`, and this plan. A focused regression
changes the prior control revision and runs actual scope collection/publication
through emitted full-scope and label assertions. Run pipeline with actual T2
integration enabled, review-scope and recheck suites. Repeat the live workflow
from trusted main after review and merge; no installed adapter change is needed.

Version impact: none. Internal CI publication only.
Documentation impact: none. Uses the already documented conservative fallback.

## Live acceptance follow-up: GraphQL resolution permission

Run 34828892963 posted the bot's resolved-verdict evidence reply, then GitHub
refused the thread mutation. Its installation-token GraphQL interface requires
contents write in addition to PR write (github/gh-aw#35726). Grant contents
write only to the existing trusted publisher job. Target/model jobs retain
read-only permissions, and the publisher still executes no PR code or merge
operation. Observe actual thread resolution; a posted verdict is insufficient.

Declared files: `.github/workflows/pr-review.yml`,
`tests/build/ci_pr_review_workflow_test.py`,
`docs/quality/2026-09-10-pr-agent-netcup-operations.md`,
`apps/docs-site/docs/operations/testing-and-proof.mdx`, and this plan.
Run workflow tests, actionlint with ShellCheck, and docs-site check; review via
trusted-main dispatch, merge, then repeat the complete live recheck.

Version impact: none. Internal CI permissions only.
Documentation impact: required. Document the actual publisher permission.
Affected portal pages: /operations/testing-and-proof

## Live acceptance follow-up: canonical Git object IDs

Run 34830825814 retained a fix diff with nine-digit object abbreviations; a
fresh collector emitted eight digits for the same Git objects, so publisher
byte comparison correctly refused the differing request. Use `git diff
--full-index` for repair evidence, independently of repository object count and
`core.abbrev`. Preserve exact source/diff/conversation comparison.

Declared files: `scripts/ci/review_recheck.py`,
`tests/build/ci_review_recheck_test.py`, and this plan. The new regression uses
a real temporary Git repository and actual collectors under core.abbrev=8 and
12, asserts identical full requests and 40-digit object IDs, and retains the
causal changed lines. Run recheck, workflow and pipeline suites, then repeat
trusted-main live publication after source review/merge. No adapter reinstall.

Version impact: none. Internal evidence encoding only.
Documentation impact: none. Restores the documented exact-request behavior.
