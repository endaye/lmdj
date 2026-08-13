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

Verified state: Run and describe only `scripts/release.sh audit --remote --tag TAG`; no mutation yet.

Next authorization: After audit, name exactly one next stable transition and request authorization for that boundary.

Unperformed states: Enumerate prepare, tag push, Draft, publication, deployment, and Channel as applicable; all are unperformed.

For a later boundary-specific authorized turn, the entire response/action is exactly:

Verified state: Audit first and report the current state.

Next authorization: Execute exactly the named one stable mutation if the gate passes, rerun audit, then name one next boundary without executing it.

Unperformed states: Enumerate all later transitions as unperformed.

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
Deployment and Channel promotion as separate, unperformed boundaries until
each is explicitly authorized and independently verified.
