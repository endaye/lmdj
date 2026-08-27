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
exit: skill:.agents/skills/lmdj-release/SKILL.md
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

## How to apply

When a Product Build snapshot and post-freeze current-page edits land in the
same squash, generate the witness with
`scripts/architecture-portal.sh witness PRODUCT_BUILD INTRODUCING_REVISION`
against the exact `main` SHA the squash produced, and verify it before treating
the Product Build as allocated. A witness is only accepted when it exactly
rebuilds the authenticated source tree and commit in a temporary Git index;
never hand-edit an immutable snapshot to make provenance agree.
