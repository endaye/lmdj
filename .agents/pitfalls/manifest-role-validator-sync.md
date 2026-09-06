---
id: manifest-role-validator-sync
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/issues/354
    observed_by: claude-code/fable-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/34017836312
    observed_by: grok-4.6
exit: skill:.agents/skills/lmdj-release/SKILL.md
---

# A manifest producer gaining a new asset role must update the deployment validator in the same change

## Why

`apps/web-runtime-host/tools/package.py` and
`apps/web-runtime-host/tools/deployment_smoke.py` encode the same manifest
asset-role vocabulary in two places. Commit 62926487 taught the producer a new
`product_identity` role but not the validator's `ALLOWED_ASSET_ROLES`, so
every host build from that commit on packaged, signed, released, and passed
all suites — then failed the deployment smoke on the staged draft (#354,
lmdj-v1.0.36.0). The suites missed it because the smoke test fixture's
ASSET_LAYOUT is a third copy of the vocabulary, which also lacked the role.

## How to apply

- When package.py starts emitting a new manifest asset role (or drops one),
  change `ALLOWED_ASSET_ROLES` (and SINGLETON_ASSET_ROLES if exactly-one) in
  `deployment_smoke.py` and the fixture ASSET_LAYOUT in
  `deployment_smoke_test.py` in the same commit.
- Do not add a new role to SINGLETON_ASSET_ROLES unless every prior published
  build also satisfies it: the deploy run baselines the previous published
  deployment with the same validator, so an exactly-one rule on a new role
  fails the rollback anchor. Creator 3.0.0's `perform_master_tap_worklet`
  is the recurrence: `_creator_required_roles()` keeps the six-role inventory
  on 3.x and the five-role inventory on 2.x priors. Preflight already verified
  the signed candidate; a failed prior-identity discovery is not a failed
  Release.
- Recurrence 2 absorbed that Creator split into the shared smoke validator
  and the release skill. A mechanical producer-vs-validator comparison still
  needs a shared constant; that remains a later refactor, not a reason to
  leave this entry open.
