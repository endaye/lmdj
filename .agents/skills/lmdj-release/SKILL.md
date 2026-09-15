---
name: lmdj-release
description: Use when auditing or operating an LMDJ tag, Draft Release, Release publication, Runtime deployment boundary, or Channel promotion.
---

# LMDJ Release

One overall release authorization covers its scoped transitions; each transition
remains a separate verification boundary. Explicit narrower user restrictions win.

## Authority and execution

Before responding, read `docs/governance/git-workflow.md`,
`docs/governance/version-management.md`,
`docs/release-evidence/release-intents.json`, and
`docs/design/2026-08-13-lmdj-standard-release-pipeline-design.md`.
Read current `AGENTS.md` for standing authorization. Resolve the exact tag,
candidate, deployment targets and Channel from the request and established
configuration. Ask only when that scope is missing or ambiguous, not merely
because the next covered transition changes external state.

Begin release operations with `scripts/release.sh audit --remote --tag TAG`.
For an audit-only, design or development request, keep release mutations out of
scope. For an authorized release, execute covered transitions sequentially,
verify each result, and continue without renewed approval while its gates pass.
A boundary-specific restriction still stops at that boundary. This permission
does not imply an unattended controller exists or that credentials are usable.

Only a verified releasable intent admits new preparation/tag/Draft/publication.
For an already published identity, audit and verify it without republishing or
rewriting history; continue only any separately verified, covered deployment or
promotion still due. An allocated identity needs candidate evidence and a
reviewed releasable intent first. Refuse abandoned or superseded-unreleased
identities. Stop on unknown, conflict, unverifiable or external-error; report
the last verified state, evidence and remedy. Never turn a failed gate into a
new approval prompt that would bypass it.

Report publication, each Deployment, Channel promotion and remaining work
separately. Do not relabel historically completed states as unperformed.
Missing external authentication, required external approval, scope expansion
and unresolved product decisions are real stops. Never forge an owner-only
review waiver or manual acceptance, or alter protection to continue.

## Command mapping

The single sequential entry is `scripts/release.sh run --authority REF [--tag TAG]
[--base-revision SHA]`, with read-only progress `scripts/release.sh status
[REQUEST_ID]` and continuation `scripts/release.sh resume REQUEST_ID`. `run`
freezes one request from the authenticated canonical control and drives it
through the one ordered driver; `resume` continues that same request ID and
re-verifies each far side without replaying an unresolved intent. Both refuse
before creating a request while any step still lacks an enrolled carrier, and
they list those steps instead of starting a partial run. A journal record is a
progress record, not external proof.

Use `scripts/release.sh prepare TAG`, `scripts/release.sh push-tag TAG`, and
`scripts/release.sh create-draft TAG` in order when covered and admissible.
Use `scripts/release.sh verify-draft TAG RELEASE_ID PLAN_SHA256` only for
read-only Draft verification. Use
`scripts/release.sh verify-published TAG RELEASE_ID PLAN_SHA256` for the
read-only post-publication Release check. Audits before and after
pre-publication mutations use `scripts/release.sh audit --remote --tag TAG`;
publication is followed by `verify-published`.

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
The written files ship as a reviewed docs Pull Request under the current Git workflow.
`stable` is refused; the open question it points at is the authority, not this
skill. Promotion requires a published intent and both Host deployments to have
succeeded; it is a separate boundary from deployment and does not follow from it.

## Full exact-main CI evidence

Current prospective policy is `complete-test-v2`: the Owner explicitly references
exactly one passed, complete 16-suite source for the exact candidate in a reviewed
intent: old `self-test-v1` via `self_test_evidence`, or full incremental evidence
via `batch_test_evidence`, together with the actual executor run ID. No reference,
mixed references, focused/none batches or legacy fourteen-lane scope qualify.
The tool verifies stable source and main ancestry, distinct control/target
revisions, attempt, current policy and digest; a green summary or AI label
is not evidence. Batch evidence additionally requires original origin/admission
controller artifacts (trusted durable-claim attestation, not latest journal
replay), the complete three-file verdict bundle and authenticated API jobs.
See the version governance for the closed reference fields and cutover.

An existing valid complete verdict may be reused for the same exact target,
including retained historical daily/node evidence. Fresh complete verification
uses `self-test-report.yml` on ref `main`, `batch_operation=reconcile`, and
`batch_request={"id":"<stable-request-id>","kind":"candidate","target":"<exact-main-SHA>"}`.
Leave `journal_config` empty to use the repository's authenticated fixed scheduler.
Use `kind=node` for an explicit diagnostic rather than candidate selection.
Both kinds request all 16 suites and share the durable execution budget;
neither moves automatic processing progress or authorizes a release.
Redelivering the same ID and target reconciles the original request; a genuinely
new test needs a new ID. Do not use lane selection, a queue ticket, or a SHA as
the dispatch ref. The trusted control revision may be newer than the candidate.
Record only validated artifacts' facts; never invent or backfill a reference.

Verdict artifacts currently retain 30 days. Missing/expired evidence is
`unverifiable`; mismatched, incomplete or non-passing evidence is `conflict`.
Recovery requires a new explicit request ID on main for the same target and a separately
reviewed intent update, not Re-run jobs: the producer currently accepts attempt
1 only. Only actually `published` history may use the recorded attempt without
re-adjudicating ephemeral retention; allocated/abandoned/superseded is not this
exception. Immutable tag/signature/Release/assets and exact plan-marker proof
remain required. Batch `lmdj.release-plan-marker.v3` permanently binds the entire
reference including `executor_event`; old self-test v2 and legacy v1 remain
unchanged. An old marker cannot prove a newly added batch reference. Never
rewrite history or infer executor event from the queue request kind.

A full dispatch is evidence, not authorization: completing one authorizes no
tag, Draft, publication, deployment or promotion.

When a verified Draft is ready and publication is covered, dispatch the protected
`publish-release.yml` on main using its verified `tag`, `release_id`, and
`plan_sha256`, wait for the exact run and verify publication. Do not approve
someone else's required approval or bypass the protected `release` Environment.
After verified publication, ship an evidence-only reviewed PR recording the
observed Release and changing its intent to published; verify the live main
ledger and rerun audit. Publication does not update that ledger automatically,
and promote requires a published intent. Do not change the candidate target or
rewrite the published Release during this handoff.
Then dispatch each covered Host deployment using the exact tag, verify its
retained evidence, and continue to covered Channel promotion through its normal
reviewed PR. Report only independently verified status; Release publication
alone never proves Deployment or Channel promotion. If publication is not
covered, report the verified inputs without dispatching.

If `publish-release.yml` fails at `verify-published`, read the live Release by
numeric ID and compare it with the immutable plan before concluding publication
failed. If it fails earlier, treat publication as not done and diagnose the
failure before retrying; see
[`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).

## Pitfalls

Open the entries below before the step each one names. They are recorded
recurrences from this repository's own history, not general advice; the
contract is [`docs/governance/pitfall-ledger.md`](../../../docs/governance/pitfall-ledger.md).

- Before treating a Product Build as allocated —
  [`squash-witness-provenance`](../../pitfalls/squash-witness-provenance.md).
  A squash rewrites the introducing commit, so a snapshot frozen from a branch
  SHA loses its provenance. Avoid needing the witness at all: freeze the
  snapshot as the first and only commit on a branch cut from the current `main`
  and merge it before `main` moves, so the squash parent is the recorded source
  revision. Generate the witness for the exact post-squash
  `main` SHA with `scripts/docs-site.sh witness PRODUCT_BUILD
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
- When diagnosing a failed `publish-release.yml` job —
  [`post-publish-audit-releasable-ledger`](../../pitfalls/post-publish-audit-releasable-ledger.md).
  For a `verify-published` failure, read the live Release by numeric ID and
  compare it with the immutable plan; for an earlier failure, treat publication
  as not done and diagnose before retrying.
- Before treating a failed Creator deploy as a failed signed-archive verify —
  [`manifest-role-validator-sync`](../../pitfalls/manifest-role-validator-sync.md).
  Prior identity discovery must accept the live Host's inventory. Creator 3.x
  smoke still requires `perform_master_tap_worklet`; Creator 2.x priors have
  five roles. Preflight already verified the candidate Release.

When a release operation exposes a new process invariant, record it through the
Pitfall Ledger step in
[`.agents/skills/issue-done/SKILL.md`](../issue-done/SKILL.md) rather than
leaving it in a report.
