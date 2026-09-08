# LMDJ Port Name Validation Unification Implementation Plan

**Goal:** Make every boundary that accepts an Artifact port name enforce the
Capability Contract's rule, so a name that could never be registered is
rejected on arrival with an accurate error.

**Architecture:** The Contract defines `port_name` as `^[a-z][a-z0-9_]*$`, but
only Provider registration enforced it. Three other boundaries applied
file-identifier rules instead, which are both wider and semantically wrong: a
port name is never a file name. This exports one definition from `provider-sdk`
and points every boundary at it. No Contract document changes.

Origin: `docs/quality/2026-08-03-review-backlog.md` unit B, item B2, from
`2026-08-03-build-1.0.8.0-review.md` finding 1. The Contract itself was
introduced by
`docs/plans/2026-08-01-lmdj-capability-v2-port-bindings.md`; this
plan repairs the enforcement gap that one left.

## Tasks

- [x] Export `lmdj::provider::valid_port_name` and delete the file-static copy
  in `registry.cpp`.
- [x] Use it in `attempt_store.cpp` read-back and `application.cpp` request
  parsing, replacing `valid_file_id` and `safe_file_id`.
- [x] Advertise `PORT_NAME_PATTERN` in the MCP tool Schema so a client cannot
  generate a structurally valid request no Capability could match.
- [x] Separate the unknown-port error from the generic artifact error.
- [x] Cover the tightened Host boundary and prove it by mutation.
- [x] Carry the version cascade and run the integrated Proof.

## Before and after

| Boundary | Was | Now |
| --- | --- | --- |
| Provider registration | `valid_port_name` | unchanged, now shared |
| Facade request parsing | `safe_file_id` | `provider::valid_port_name` |
| Attempt read-back | `valid_file_id` | `valid_port_name` |
| MCP tool Schema | `FILE_ID_PATTERN` | `PORT_NAME_PATTERN` |

`validate_request` previously folded four distinct failures into
`"capability request artifacts are invalid"`. An unknown port now reports
`"capability request names a port the Capability does not declare"` and a
malformed name reports `"capability request port name is invalid"`.

No request that previously succeeded can now fail: every name the tightened
rule rejects was already rejected downstream by `find_port` returning null.
The rejection moves earlier and names its reason.

## Verification

`facade.application` gained five rejected port names (`Source`, `in-put`,
`with.dot`, `_leading`, empty). Reverting `application.cpp` to `safe_file_id`
fails that test, so the assertion has teeth.

The repository's own gates caught four things this plan initially missed, each
a place Provider version identity is pinned: the two Provider manifests
(`module_graph_test.py`), the Provider registration version in
`providers/*/src/provider.cpp`, the `provider_version` baked into the
source-package descriptor in `providers/*/CMakeLists.txt`, and the
`ProviderRegistration` version inside the `assembly_loader` test catalog. All
are now consistent and the integrated Proof reports Assembly lock MATCH.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.11.0` | `1.0.12.0` | Runnable Assembly input validation and the advertised MCP tool Schema change. |
| `provider-sdk` | `1.0.0`, API 2 | `1.1.0`, API 2 | Adds public `valid_port_name`; purely additive. |
| `application-facade` | `1.1.0`, API 2 | `1.1.1`, API 2 | Exact dependency change plus a backward-compatible boundary tightening. |
| `core-cli` | `1.0.2`, API 2 | `1.0.3`, API 2 | Exact Facade dependency change only. |
| `core-mcp` | `1.0.2`, API 2 | `1.1.0`, API 2 | The advertised tool Schema narrows, which is observable to clients. |
| `native-test-host` | `1.0.0`, API 1 | `1.0.1`, API 1 | Exact Facade dependency change only. |
| Proof Providers | `1.0.0`, API 2 | `1.0.1`, API 2 | Exact `provider-sdk` dependency change; source-package identity is rehashed. |
| Contracts | unchanged | unchanged | No Schema document is edited. `port_name` already said `^[a-z][a-z0-9_]*$`. |
| Capabilities / Models | unchanged | unchanged | No Capability or model identity changes. |

- This Product Build number assumes this Task merges before backlog units C
  and D. If another Product-Build-bumping Task merges first, renumber during
  rebase; only one Task may hold `1.0.12.0`.
- Compatibility: no Project migration. Terminal Attempts written by earlier
  Builds remain readable, because every port name they contain was registered
  and therefore already satisfies the stricter rule.
- Regenerate `products/lmdj/assembly.lock.json` with `scripts/version.py lock`
  after the Provider source edits, since the source-package hashes change.
- Rollback reuses immutable Product Build `1.0.11.0`.
- No tag, Release, Channel promotion, or deployment is authorized.

## Follow-up found while implementing

`tests/build/version_test.py` pins the own-version of every Module except
`provider-sdk`, which appears only as a dependency of `application-facade`.
That gap is pre-existing and out of scope here; it belongs in a Task that
audits the version-pinning coverage itself.
