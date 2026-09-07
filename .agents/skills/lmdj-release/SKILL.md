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

On a fresh clone or a fresh runner workspace, run `scripts/release.sh hydrate`
before the first audit. It is the only stable subcommand that writes the local
Git object store: it fetches by SHA exactly the release intent target objects
the clone lacks, prints what it hydrated versus what was already present, and is
idempotent, so running it unconditionally is safe. It authorizes nothing — no
tag, Draft, publication, deployment or promotion follows from it. The audit
itself never fetches on miss, so an absent target is a reported finding whose
remedy names this command.

Channel promotion is `scripts/release.sh promote TAG CHANNEL --deployment-run
HOST=RUN_ID ... [--evidence PATH ...]`. It is a local mutation of the ledger and
one evidence document only: it audits first, verifies every Host deployment
run's retained evidence for the exact tag, and never edits the GitHub Release.
The written files ship as a docs Pull Request through the Integration Queue.
`stable` is refused; the open question it points at is the authority, not this
skill. Promotion requires a published intent and both Host deployments to have
succeeded; it is a separate boundary from deployment and does not follow from it.

## Full exact-main CI evidence

Current prospective policy is `self-test-v1`: the Owner explicitly references
one passed, complete 16-suite self-test for the exact candidate in the reviewed
intent's `self_test_evidence` and run ID. The tool verifies stable workflow and
main ancestry, distinct control/target revisions, attempt, policy and digest;
neither a green summary nor legacy `full`/`requested` scope is sufficient.
See the version governance for the closed reference fields and cutover.

An existing valid daily or node verdict may be reused for the same exact target.
If fresh evidence is required, separately authorize `ci.yml` dispatch on ref
`main` with `target_revision` equal to the candidate SHA (not a SHA as ref).
Use the self-test inputs, without lane selection or a queue ticket. The trusted
control revision may be newer than the candidate. Record only the validated
artifact's facts; never invent or backfill a digest or reference.

Verdict artifacts currently retain 30 days. Missing/expired evidence is
`unverifiable`; mismatched, incomplete or non-passing evidence is `conflict`.
Recovery requires a new dispatch on main for the same target and a separately
reviewed intent update, not Re-run jobs: the producer currently accepts attempt
1 only. Published legacy and self-test history remains read-only, with immutable
tag/Release/asset/plan-marker verification; artifact expiry does not rewrite it.

A full dispatch is evidence, not authorization: completing one authorizes no
tag, Draft, publication, deployment or promotion.

When a verified Draft is ready for publication, print the protected workflow
inputs `tag`, `release_id`, and `plan_sha256`. Do not approve the protected
`release` Environment or claim publication on the user's behalf. Keep
Deployment and Channel promotion separate; report only independently verified
status and never infer either from Release publication.

If `publish-release.yml` exits non-zero after the `publish-draft` step printed
`release status: published`, read the live Release by numeric ID before
concluding publication failed. Canonical `audit --remote` loads the still-
`releasable` ledger from protected `main`, so
`non-published intent identifies an already published GitHub Release` is the
expected post-PATCH finding until a docs Pull Request records
`disposition: published`. Do not retry the workflow. See
[`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).

## Pitfalls

Open the entries below before the step each one names. They are recorded
recurrences from this repository's own history, not general advice; the
contract is [`docs/governance/pitfall-ledger.md`](../../../docs/governance/pitfall-ledger.md).

- Before treating a Product Build as allocated —
  [`squash-witness-provenance`](../../pitfalls/squash-witness-provenance.md).
  A squash rewrites the introducing commit, so a snapshot frozen from a branch
  SHA loses its provenance. Generate the witness for the exact post-squash
  `main` SHA with `scripts/architecture-portal.sh witness PRODUCT_BUILD
  INTRODUCING_REVISION` and verify it; never hand-edit an immutable snapshot to
  make provenance agree.
- Before running any audit from a fresh clone or workspace —
  [`release-intent-target-reachability`](../../pitfalls/release-intent-target-reachability.md).
  An allocated intent can record a pre-squash target no advertised ref reaches,
  so the clone lacks the object and the audit correctly reports the intent
  unverifiable. Run `scripts/release.sh hydrate` first; never add an inline
  fetch copy of your own and never make the audit self-heal.
- Before creating or binding a release intent —
  [`release-intent-binding`](../../pitfalls/release-intent-binding.md).
  Allocation needs no intent. Bind the intent only after the exact
  protected-main squash SHA exists; a pre-squash or branch SHA is not a
  protected-main ancestor and fails closed.
- Before treating a red `publish-release.yml` job as an unpublished Release —
  [`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).
  After `publish-draft` succeeds, the in-workflow `audit --remote` still reads
  canonical `main`'s `releasable` row. Read the live Release; do not retry.
- Before treating a failed Creator deploy as a failed signed-archive verify —
  [`manifest-role-validator-sync`](../../pitfalls/manifest-role-validator-sync.md).
  Prior identity discovery must accept the live Host's inventory. Creator 3.x
  smoke still requires `perform_master_tap_worklet`; Creator 2.x priors have
  five roles. Preflight already verified the candidate Release.

When a release operation exposes a new process invariant, record it through the
Pitfall Ledger step in
[`.agents/skills/issue-done/SKILL.md`](../issue-done/SKILL.md) rather than
leaving it in a report.
