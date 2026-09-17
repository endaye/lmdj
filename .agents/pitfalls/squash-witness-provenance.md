---
id: squash-witness-provenance
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-12
    occurrence: https://github.com/endaye/lmdj/pull/129
    observed_by: unknown
  - date: 2026-08-14
    occurrence: https://github.com/endaye/lmdj/pull/139
    observed_by: unknown
  - date: 2026-08-16
    occurrence: https://github.com/endaye/lmdj/pull/169
    observed_by: unknown
  - date: 2026-08-16
    occurrence: https://github.com/endaye/lmdj/pull/179
    observed_by: unknown
  - date: 2026-08-24
    occurrence: https://github.com/endaye/lmdj/pull/289
    observed_by: unknown
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/pull/334
    observed_by: claude-fable-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/681
    observed_by: claude-opus-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/pull/689
    observed_by: grok-4.6-build
  - date: 2026-09-07
    occurrence: https://github.com/endaye/lmdj/pull/761
    observed_by: Codex
  - date: 2026-09-16
    occurrence: https://github.com/endaye/lmdj/pull/1417
    observed_by: Kimi Code CLI
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A squash merge rewrites the introducing commit, so an immutable Portal snapshot loses its provenance unless a squash witness is generated for the exact resulting `main` SHA.

## Why

The snapshot records the revision it was frozen from. Protected `main` accepts
only squash merges, so the SHA the snapshot names never becomes a `main`
commit, and the introducing tree on `main` may additionally contain mutable
current-page updates made after the freeze. The verifier fails closed in that
state, which is correct: it cannot rebuild the authenticated source tree from
ancestry alone.

Detection was never the gap. The audit failed closed all five times; what was
missing each time was the procedural knowledge that the witness has to be
produced for the exact post-squash SHA, so the repair always happened after the
fact, in a follow-up Pull Request, against a Product Build that had already
been allocated. Four repairs (1.0.16.9, 1.0.21.0, 1.0.22.0, 1.0.23.0) preceded
the fifth on 1.0.31.0.

## A local pass in the authoring worktree proves nothing

The 2026-09-06 recurrence inverted the usual failure. `check:release-docs` was
run against merged `main` from the same worktree that had produced the branch,
reported `snapshot matches repository truth`, and was read as proof that no
witness was needed; PR #681 was opened asserting exactly that, and was closed as
superseded once the witness landed through #682.

That repository still held the pre-squash source commit object, so the verifier
resolved the recorded source revision directly instead of falling back to the
frozen raw commit bytes. A fresh clone and CI hold no such object and fail
closed, which is why the witness is required.

Verify post-squash provenance from a clone that never held the branch, or
simply write the witness: it is the cheaper of the two, and a witness for a
genuinely non-divergent squash costs one file.

## How to apply

Prevent it first. Direct-parent provenance resolves with no witness when the
commit introducing the metadata has the recorded source revision as its parent.
The freeze records the HEAD it ran against, and a squash merge makes that parent
`main`'s tip at merge time, so the two agree only when the freeze is the first
and only commit on a branch cut from the current `main`, merged before `main`
moves. A freeze bundled into a branch that already carries commits records a
branch commit the squash discards, and no arrangement of the merge can recover
it. Every snapshot frozen so far (1.0.52.0 through 1.0.57.0) recorded such a
branch commit, and five of the six then needed a witness: this entry's
recurrences are that bundling, not bad luck at merge time.

The detection also moved earlier. The full Architecture Portal lane in `ci.yml`
is conditioned on the main incremental-batch fixed-target mode, so no Pull
Request ever ran it and a broken snapshot surfaced only on the next main run:
that is how Build 1.0.57.0 was found, already merged. The `Architecture Portal
provenance` job in `pr-contract.yml` now runs the same portal lane commands
against the Pull Request head whenever the change selects the portal lane, so
the repair is decided before merge instead of after.

When a Product Build snapshot and post-freeze current-page edits land in the
same squash, generate the witness with
`scripts/architecture-portal.sh witness PRODUCT_BUILD INTRODUCING_REVISION`
against the exact `main` SHA the squash produced, and verify it before treating
the Product Build as allocated. A witness is only accepted when it exactly
rebuilds the authenticated source tree and commit in a temporary Git index;
never hand-edit an immutable snapshot to make provenance agree.

The 2026-09-07 recurrence was found while integrating CI work after the manual
merge of the Product Build cut. Release-only guidance did not reach that
ordinary task-shipping boundary: the next unrelated Portal check found the
missing witness. The exit now also lives in `issue-done`'s post-merge step,
conditionally for Tasks allocating a Build or introducing a snapshot; it does
not require every unrelated Task to run a new post-merge Portal build.
