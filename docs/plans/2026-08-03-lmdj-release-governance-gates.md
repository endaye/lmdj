# LMDJ Release Governance Gates Implementation Plan

**Goal:** Stop the packager from emitting an artifact that claims a Channel gate
it never ran or a Git revision that does not describe its contents, and give a
consumer one out-of-band integrity signal.

**Architecture:** `scripts/core.sh package` runs the unit and component tiers
before packaging, because the artifact is stamped `canary` and
`version-management.md` §3 requires basic unit tests for that Channel.
`package-core.py` refuses a modified working tree by default and writes a
detached `.sha256` beside the archive. No Module, Contract, or Assembly member
changes.

Origin: `docs/quality/2026-08-03-review-backlog.md` unit D, items D1 and D2,
from `2026-08-03-build-1.0.9.0-review.md` findings 1, 3, and 4. The packager was
created by `docs/plans/2026-08-01-lmdj-core-distribution-package.md`.

## Tasks

- [x] Gate `scripts/core.sh package` on `ctest --preset release -L
  '^(unit|component)$'`.
- [x] Refuse to package a modified working tree, with an explicit opt-out for
  the mechanics test.
- [x] Emit a detached `<archive>.sha256` in `shasum -c` format and assert it.
- [x] Record D3 and D4 as open questions rather than settling them.

## Where the provenance gate belongs

The backlog proposed putting the cleanliness check in `_git_revision()`. That
was tried and reverted: `scripts/core.sh proof` calls `version.py manifest`, so
the check would fail `proof` for any developer with uncommitted work. Measured
directly before reverting — `version error: refusing to record a Git revision
for a modified working tree`.

The gate belongs at the boundary that produces a **distributable**, not in the
shared Manifest generator. `proof` legitimately builds a Manifest from a working
tree for local verification; only a package leaves the machine.

The same trap caught the acceptance test. It invokes the packager directly and
asserts exit 0, so a strict default would have broken it — and `proof` runs it.
It now passes `--allow-modified-worktree` with a comment stating it exercises
packaging mechanics, not release provenance. The default stays strict, so
`core.sh package` and any direct call are gated.

## What is deliberately not fixed

Two of the four items in backlog unit D are decisions, not defects, and
`CLAUDE.md` forbids settling a product-level question inside an implementation
Task. Both are now in `docs/prd/open-questions.md`:

- **Reproducible archives (D3).** `create_zip()` already fixes timestamps,
  ordering, and file modes, but `build-manifest.json` sits inside the archive
  and carries `build_time`, so the bytes differ on every run. `build_time` is
  required by `version-management.md` §4, so this is not an implementation
  defect — it is two correct requirements in one container. Moving the Manifest
  out changes the shape of a published artifact.
- **`native-test-host` (D4).** It is an Assembly member shipped in every
  package while its Module id says "test". Either the name or the boundary is
  wrong, and correcting the name is a Module rename plus an Assembly change.

The related gap — no written rule for what may enter a distribution package —
is recorded with D4. Between `1.0.9.0` and `1.0.11.0` the package grew from
CLI + MCP + library to include that Host with no rule constraining it.

`validate_manifest()`'s near-tautological lock comparison (1.0.9.0 finding 6)
is left alone; it is harmless and removing it is unrelated to these gates.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

**Version impact: none.**

- Product Build: unchanged. No Assembly member, Module API, Host protocol, or
  runnable Product behavior changes. The packaging tool gains gates; the
  packaged Assembly is identical.
- Core Modules, Hosts, Providers, Models: unchanged. No file under `packages/`,
  `apps/`, `providers/`, or `products/` is touched.
- Contracts: unchanged. `lmdj.build-manifest.v1` gains no field; the detached
  checksum is a sibling file, not part of the Manifest.
- Changed files are `scripts/`, `tests/`, and `docs/`, which carry no version
  identity.
- No tag, Release, Channel promotion, or deployment is authorized.
