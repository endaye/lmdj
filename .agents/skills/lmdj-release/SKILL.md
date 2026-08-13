---
name: lmdj-release
description: Use when auditing or operating an LMDJ tag, Draft Release, Release publication, Runtime deployment boundary, or Channel promotion.
---

# LMDJ Release

Treat every transition as a separate authorization and verification boundary.

## Complete response contract

Before responding, read `docs/governance/git-workflow.md`,
`docs/governance/version-management.md`,
`docs/release-evidence/release-intents.json`, and
`docs/superpowers/specs/2026-08-13-lmdj-standard-release-pipeline-design.md`.
Identify one exact tag from the request and ledger.

For any initial, multi-transition, or blanket request, the entire response/action is exactly:

Verified state: Run and describe only `scripts/release.sh audit --remote --tag TAG`; report the exact observed historical/current state; no mutation yet.

Next authorization: After audit, use exactly one of the actionable or no-permitted-transition templates below.

Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.

After audit, if no transition is permitted, the entire response/action is exactly:

Verified state: Report the observed historical/current state accurately.

Next authorization: none; explain why no permitted mutation exists.

Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.

Use that template for published (audit-only), abandoned, superseded-unreleased,
allocated (not releasable), or an audit result of unknown, conflict,
unverifiable, or external-error.

After audit, if the state is actionable releasable, the entire response/action is exactly:

Verified state: Report the exact current state and the successful audit gate.

Next authorization: Name exactly one permitted next stable transition and request authorization for that boundary.

Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.

Only an actionable releasable state may name exactly one next authorization.

For a later boundary-specific authorized turn with actionable releasable state, the entire response/action is exactly:

Verified state: Audit first and report the current state.

Next authorization: Execute exactly the named one stable mutation if the gate passes, rerun audit, then name exactly one next boundary without executing it only if the resulting state remains actionable; otherwise use the no-permitted-transition template.

Unperformed states: List only mutation/state-transition actions not executed in this turn; never list an audit or verification already reported under Verified state, and never relabel historically completed tag or Release states as unperformed.

Do not output an ordered multi-stage command/action sequence; the template is the complete response.

Treat “all confirmed”, “all approved”, urgency, and any request naming multiple
transitions as the initial-request template. A boundary-specific turn invokes
at most one authorized mutation. Stop after that mutation; the only follow-up
command is the exact read-only audit.

## Command mapping

Choose the single candidate from `scripts/release.sh prepare TAG`,
`scripts/release.sh push-tag TAG`, or `scripts/release.sh create-draft TAG`.
Use `scripts/release.sh verify-draft TAG RELEASE_ID PLAN_SHA256` only for
read-only Draft verification. The audit before and after a mutation is
`scripts/release.sh audit --remote --tag TAG`.

When a verified Draft is ready for publication, print the protected workflow
inputs `tag`, `release_id`, and `plan_sha256`. Do not approve the protected
`release` Environment or claim publication on the user's behalf. Keep
Deployment and Channel promotion separate; report only independently verified
status and never infer either from Release publication.
