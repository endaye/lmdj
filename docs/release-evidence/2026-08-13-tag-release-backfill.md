# 2026-08-13 tag and Release backfill inventory

## Boundary

This dated inventory is a reviewed migration baseline for the closed release
control plane. It is not a cache of remote state: a fresh read-only audit of
canonical Git/GitHub is authoritative and wins if it differs from this snapshot.

The 14 new backfilled GitHub Release identities below are a subset of the full
history. The accompanying `release-intents.json` also records all 28 current-policy
formal remote tags: eleven Product tag-only identities, six published Product
Releases, and eleven published Module Releases. Additional abandoned, superseded,
and allocated Product rows are lifecycle intent, not claims that corresponding
remote tags exist.

## Formal current-policy history

- Product tag-only `1.0.1.0` through `1.0.11.0` are
  `superseded-unreleased`, with their exact protected-main targets and Core CI
  runs recorded in the ledger.
- Published Products are `1.0.13.0`, `1.0.14.0`, `1.0.15.2`, `1.0.16.5`,
  `1.0.16.8`, and `1.0.16.9`. `1.0.13.0` uses `core-package`; the later five
  use `web-runtime-host`.
- The eleven Module Releases are `source-only`; their targets are bound to
  successful Core CI runs `30751690298` or `30761741614` in the ledger.

## Historical exception: Product 1.0.15.2

`lmdj-v1.0.15.2` remains a published immutable historical Release. Its exact
main Core CI run `31193044255` was cancelled. The same target
`72ae40074620cc5681c462ba04a31a666449734f` has successful Nightly runs
`31211206448` and `31273884702`, and existing Runtime Host deployment acceptance.
The ledger therefore records the exact read-only
`pre-pipeline-ci-evidence` exception. It permits an audit finding of
`ok-with-historical-exception`; it does not authorize any mutation command.

## Legacy exceptions

The legacy GitHub Release `v0.2.0` (numeric ID `359913165`, target
`9a2811bc326d7b63e538c77eeec428f617484ebe`) and WIP tag
`wip/chameleon-2d-2026-07-26` (target
`a0f30e91d8f566eb7004430a3eb4de88cd25e4c3`) predate the current four-kind tag
syntax. They are exact, read-only `pre-governance-tag-scheme` exceptions, not
prospective release authorization.

## Deliberately non-releasable Product identities

`1.0.16.6`, `1.0.16.7`, and `1.0.18.0` are abandoned; `1.0.19.0` is
superseded-unreleased. Product `1.0.20.0` is allocated to
`f4674ada631d6af7ad8b9dd9f440671c2736d293` and is explicitly not releasable.
No row in this section claims a remote tag or GitHub Release.
