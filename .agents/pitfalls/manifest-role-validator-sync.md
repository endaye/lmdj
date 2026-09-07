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
exit: gate:apps/web-runtime-host/test/manifest_asset_role_parity_test.py
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

Both occurrences were escalations of one class: the vocabulary had no single
definition, so nothing could compare a producer with the validator. #711
removed the copies. `apps/web-runtime-host/tools/asset_roles.py` is now the
only place a role name is written; both packagers, the validator and both
smoke fixtures import it, and the gate compares the vocabulary against the
producers and against the manifest of every published Build.

## How to apply

- Add or drop a manifest asset role in exactly two places: its entry in
  `hosts.<host_id>.expected_assets` in `tools/web-runtime/runtime-identity.json`
  (regenerating `products/lmdj/generated/web-runtime-identity.json`), and the
  constant plus the matching `*_EMITTED_ASSET_ROLES` and `ALLOWED_ASSET_ROLES`
  membership in `apps/web-runtime-host/tools/asset_roles.py`. Never write a
  role as a string literal anywhere else; the gate fails on one.
- Do not make a role required — `SINGLETON_ASSET_ROLES`, or a Creator required
  inventory — unless every already published manifest under
  `apps/web-runtime-host/test/fixtures/published-host-manifests/` still
  satisfies the rule. The deploy baselines the previously published deployment
  with the same validator, so an exactly-one rule on a new role fails the
  rollback anchor. Creator 3.0.0's `perform_master_tap_worklet` is the shape:
  `_creator_required_roles()` keeps the six-role inventory on 3.x and the
  five-role inventory on 2.x priors. Preflight already verified the signed
  candidate; a failed prior-identity discovery is not a failed Release.
- When a Build publishes, retain its `host-manifest.json` from the immutable
  Release archive under that fixture directory with its `provenance.json`
  entry. Never edit a retained manifest, and never relax the validator, to
  make the gate green: the retained bytes are the evidence of what a published
  Build really carries.
