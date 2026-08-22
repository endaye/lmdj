# 2026-08-22 triage of Issue #165's 18 pre-existing remote-audit findings

## Boundary

This dated record classifies the 18 findings named by
[Issue #165](https://github.com/endaye/lmdj/issues/165). It is not a cache of
remote state: a fresh `scripts/release.sh audit --remote` of canonical
Git/GitHub is authoritative and wins if it differs.

No tag, Draft, published GitHub Release, deployment, or Channel was mutated
for this triage. Remaining GitHub Release `name` edits listed below are
separately authorized mutations. Historical exceptions remain audit-only and
do not authorize `prepare`, `push-tag`, `create-draft`, or publication.

Version impact: none. No Product Build, Module, Provider, Contract, or
Assembly identity changed.

Documentation impact: none. This is a dated release-evidence classification
plus a local exact-target false-positive fix. It does not change Product
Build, Assembly, Channel, portal identity, or the operator mutation sequence
already described on the current Version and Release page.

## Observed remote names

Live published Module Release names, all published `2026-08-13T03:48Z` after
policy `historical_cutoff` `2026-08-13T00:00:00Z`:

| Tag | Observed GitHub `name` | Current-policy expected `name` |
| --- | --- | --- |
| `module/application-facade/v1.0.1` | `application-facade 1.0.1` | `module application-facade@1.0.1` |
| `module/application-facade/v1.1.0` | `application-facade 1.1.0` | `module application-facade@1.1.0` |
| `module/audio-runtime/v0.2.0` | `audio-runtime 0.2.0` | `module audio-runtime@0.2.0` |
| `module/audio-runtime/v0.3.0` | `audio-runtime 0.3.0` | `module audio-runtime@0.3.0` |
| `module/core-cli/v1.0.1` | `core-cli 1.0.1` | `module core-cli@1.0.1` |
| `module/core-cli/v1.0.2` | `core-cli 1.0.2` | `module core-cli@1.0.2` |
| `module/core-mcp/v1.0.1` | `core-mcp 1.0.1` | `module core-mcp@1.0.1` |
| `module/core-mcp/v1.0.2` | `core-mcp 1.0.2` | `module core-mcp@1.0.2` |
| `module/native-test-host/v1.0.0` | `native-test-host 1.0.0` | `module native-test-host@1.0.0` |
| `module/project-cooker/v0.2.0` | `project-cooker 0.2.0` | `module project-cooker@0.2.0` |
| `module/project-io/v0.3.0` | `project-io 0.3.0` | `module project-io@0.3.0` |

Live published Product Release names versus current-policy `LMDJ {identity}`:

| Tag | Observed GitHub `name` | Published |
| --- | --- | --- |
| `lmdj-v1.0.13.0` | `LMDJ Product Build 1.0.13.0 · canary` | `2026-08-13T03:47:36Z` |
| `lmdj-v1.0.14.0` | `LMDJ Product Build 1.0.14.0 · canary` | `2026-08-13T03:47:47Z` |
| `lmdj-v1.0.15.2` | `LMDJ Product Build 1.0.15.2 · canary` | `2026-08-07T15:36:35Z` |
| `lmdj-v1.0.16.5` | `LMDJ Product Build 1.0.16.5 · canary` | `2026-08-10T17:51:58Z` |
| `lmdj-v1.0.16.8` | `LMDJ Product Build 1.0.16.8 · canary` | `2026-08-11T20:22:09Z` |
| `lmdj-v1.0.16.9` | `LMDJ Product Build 1.0.16.9 · canary` | `2026-08-13T03:47:53Z` |

`lmdj-v1.0.21.0` is ledger `allocated` and has no GitHub Release.

## Classification of the 18 named findings

Each Issue #165 finding has exactly one class.

| Subject | Issue #165 finding | Class | After local remediation |
| --- | --- | --- | --- |
| 11 Module tags above | `[conflict] GitHub Release name conflicts with intent identity` | GitHub Release-metadata drift | Unchanged conflict. GitHub `name` was not edited. |
| `lmdj-v1.0.13.0` | `[unverifiable] exact release target identity or support metadata is invalid` | tooling/validator drift | Exact-target false positive removed. Unmasked GitHub `name` conflict remains. |
| `lmdj-v1.0.14.0` | same unverifiable | tooling/validator drift | Same as `1.0.13.0`. |
| `lmdj-v1.0.15.2` | same unverifiable | tooling/validator drift | Same as `1.0.13.0`. Existing `pre-pipeline-ci-evidence` exception still does not waive the name conflict and still cannot authorize a mutation. |
| `lmdj-v1.0.16.5` | same unverifiable | tooling/validator drift | Same as `1.0.13.0`. |
| `lmdj-v1.0.16.8` | same unverifiable | tooling/validator drift | Same as `1.0.13.0`. |
| `lmdj-v1.0.16.9` | same unverifiable | tooling/validator drift | Same as `1.0.13.0`. |
| `lmdj-v1.0.21.0` | same unverifiable | tooling/validator drift | Exact-target false positive removed. Fresh remote audit reports `ok` (`allocated` with no remote publication). |

The seven Product unverifiable findings were not ledger drift. Their exact
target trees already bind Product identity, Assembly lock, and Portal snapshot
lock digest. The shipped validator then ran each tree's
`apps/architecture-portal/scripts/check-release-docs.mjs` inside a detached
worktree that has no `node_modules`. Historical `repo-facts.mjs` imports
`glob`, so Node reported `Cannot find package 'glob'`, and
`target_validation.py` relabeled that environment gap as
`Product Portal snapshot provenance is invalid`. That named rule is a
false positive: it is not an identity mismatch.

The 11 Module name conflicts cannot be historical exceptions.
`observed_before` must precede `historical_cutoff` `2026-08-13T00:00:00Z`, and
those Releases were published later the same day. No new exception code was
minted.

## Unmasked Product GitHub names

Once the glob false positive was removed, the six published Product tags above
surfaced `[conflict] GitHub Release name conflicts with intent identity`.
Those unmasked findings are GitHub Release-metadata drift. Expected current
policy name is `LMDJ {identity}` (for example `LMDJ 1.0.13.0`). Observed names
are `LMDJ Product Build {identity} · canary`. GitHub objects were not edited.

`lmdj-v1.0.21.0` has no unmasked GitHub metadata finding.

## Remaining separately authorized remote edits

These are not performed by this triage:

1. Eleven Module GitHub Release `name` updates from `{id} {version}` to
   `module {id}@{version}`.
2. Six Product GitHub Release `name` updates from
   `LMDJ Product Build {identity} · canary` to `LMDJ {identity}`.

Each Release `name` PATCH is its own authorization boundary.

## Out of scope on the same remote audit

The same 2026-08-22 remote audit also reported `lmdj-v1.0.22.0` and
`lmdj-v1.0.23.0` as exact-target `unverifiable` with
`source projection is neither direct-parent nor squash-equivalent and
authenticated squash witness is unavailable`, and `lmdj-v1.0.25.0` as
`unauthorized` (`release target is outside protected main ancestry`). Those
subjects are not among the 18 Issue #165 findings and were not changed here.
