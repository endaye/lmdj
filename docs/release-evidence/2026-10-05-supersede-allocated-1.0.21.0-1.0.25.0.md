# Supersede Stale Allocated Product Builds — 1.0.21.0 through 1.0.25.0

## Evidence boundary

This record moves five stale `allocated` release intents to
`superseded-unreleased` in `docs/release-evidence/release-intents.json`. It
mutates no remote state: no tag, Draft, Release, deployment, or Channel
promotion is created, moved, or deleted. The immutable Portal snapshots and
existing evidence documents for these Builds are retained unchanged as
history.

## Reason

Each of these Builds was allocated for team testing and never released. Later
Builds on the same product line and `canary` Channel — `1.0.36.0`, `1.0.40.0`,
`1.0.41.0`, `1.0.42.0`, `1.0.61.0`, and `1.0.66.0` — were published from
later protected-main revisions, so every one of these candidates is superseded
and must never be published (`abandoned` and `superseded-unreleased` intents
refuse publication under `docs/governance/version-management.md`).

## Per-Build audit (2026-10-04, UTC)

Each row is the result of `scripts/release.sh audit --remote --tag TAG`
against the live remote before the disposition change.

| Build | Target revision | Audit result |
| --- | --- | --- |
| `1.0.21.0` | `5613158240f7e31385ccb5d175bded3c245ae33b` | `ok` — allocated intent has no remote publication state |
| `1.0.22.0` | `51d9e4748cc12a4423954a159949b7b165513789` | `unverifiable` — Portal snapshot provenance invalid; squash witness unavailable |
| `1.0.23.0` | `a71b5e0ace653af29ed90b8ff5916c25e0aea0b2` | `unverifiable` — Portal snapshot provenance invalid; squash witness unavailable |
| `1.0.24.0` | `a3d13ad1e25c69be07ee74464391589127f35d1a` | `ok` — allocated intent has no remote publication state |
| `1.0.25.0` | `349a834f74e919fc34f07f029b8142db5f1293bc` | `unauthorized` — release target is outside protected main ancestry |

Independent confirmation: `git ls-remote --tags origin` and
`gh release list` show no tag or Release for any of these identities.

## Disposition change

| Tag | Old disposition | New disposition |
| --- | --- | --- |
| `lmdj-v1.0.21.0` | `allocated` | `superseded-unreleased` |
| `lmdj-v1.0.22.0` | `allocated` | `superseded-unreleased` |
| `lmdj-v1.0.23.0` | `allocated` | `superseded-unreleased` |
| `lmdj-v1.0.24.0` | `allocated` | `superseded-unreleased` |
| `lmdj-v1.0.25.0` | `allocated` | `superseded-unreleased` |
