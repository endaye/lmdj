---
id: manifest-role-validator-sync
area: ci-release
status: open
recurrences:
  - date: 2026-08-27
    occurrence: https://github.com/endaye/lmdj/issues/354
    observed_by: claude-code/fable-5
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/actions/runs/34017836312
    observed_by: grok-4.6
exit: none
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

The second occurrence kept all three copies in sync and still failed. PR #664
made the new Creator `perform_master_tap_worklet` role a required singleton
for every Creator manifest, but the deploy run validates the previously
published deployment with the same validator as its rollback anchor. The live
`1.0.41.0` Creator (Host `2.1.1`, five assets) failed `prior published deploy
identity discovery` with `manifest required asset role inventory is invalid`,
so `1.0.42.0` never reached production (Actions run 34017836312).

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
- When a new role is required for the Build that introduces it, key the
  requirement on the Host version (or manifest schema) that introduced it, and
  add the last published Build's inventory as a passing fixture in the same
  commit. A validator on `main` must accept every manifest it will be asked
  to validate: the candidate and the currently published rollback anchor.
- No gate exit yet: the version split above covers this exact recurrence, not
  the class, and a mechanical producer-vs-validator comparison still needs a
  shared constant. Recurrence 2 escalated that refactor to
  [#711](https://github.com/endaye/lmdj/issues/711), which owns the shared
  vocabulary and retained-prior-manifest gate candidates.
