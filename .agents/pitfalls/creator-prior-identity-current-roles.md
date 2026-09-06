---
id: creator-prior-identity-current-roles
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/34017836312
    observed_by: grok-4.6
exit: skill:.agents/skills/lmdj-release/SKILL.md
---

# Creator exact-tag deploy discovers the live prior with the deploying Host's required asset roles, so a 3.0.0 cut cannot read a published 2.1.1 five-asset inventory as rollback identity.

## Why

`scripts/creator-web-deploy.sh` records exact-prior rollback by running
`discover-identity` against the currently published Creator Site, then HTTP and
browser smoke with that identity. Creator 3.0.0 added the hashed
`perform_master_tap_worklet` singleton. The shared smoke validator required
that six-role inventory for every `creator-web` manifest, including the live
`1.0.41.0` / `2.1.1` prior.

`deploy-creator-web.yml` run `34017836312` therefore failed after preflight
had already verified the signed `lmdj-v1.0.42.0` archive:
`manifest required asset role inventory is invalid` then
`prior published deploy identity discovery failed`. Runtime 3.0.0 did not hit
this because its required roles did not change.

The class is the same never-exercised-path family as
[[github-release-asset-url-rewrite]]: the first `web-hosts` cut that adds a
Creator-only required role is the first time prior discovery runs against a
narrower live inventory.

## How to apply

Keep the 3.x Creator smoke on the six-role inventory, including
`perform_master_tap_worklet`. Prior identity discovery and smoke must accept
the 2.x five-role Creator inventory (`capture_worklet`, `host_main`,
`host_style`, `runtime_script`, `runtime_wasm`) so exact-prior rollback can
be recorded. Do not treat a failed prior-identity discovery as a failed
Release verification; preflight already checked the signed candidate.
