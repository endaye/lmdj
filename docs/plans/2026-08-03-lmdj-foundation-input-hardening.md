# LMDJ Foundation Input Hardening Implementation Plan

**Goal:** Give every deserialization boundary one depth-bounded JSON entry
point and one UTF-8 validator.

**Architecture:** `parse_bounded_json` and `valid_utf8` move into
`packages/foundation`, which every Core Module already depends on. The seven
disk read paths in `project-io` and `provider-sdk` that parsed unbounded JSON
now route through it, and the copies inside `application-facade` are deleted.
`read_json` is left to the storage platform: see the withdrawal below.

Origin: `docs/quality/2026-08-03-review-backlog.md` unit C, covering
`2026-08-03-build-1.0.7.0-review.md` findings 1 and 3 and
`docs/quality/2026-08-01-core-review.md` finding 3. The limit itself was
introduced at the Host boundaries by
`docs/plans/2026-08-01-lmdj-json-depth-limit.md`; this plan extends
it inward and corrects that plan's stated mechanism.

## Tasks

- [x] Add `kMaximumJsonContainerDepth`, both `parse_bounded_json` overloads, and
  `valid_utf8` to `foundation`, with a mutation-verified unit test.
- [x] Route all seven `project-io` and `provider-sdk` disk parses through it.
- [x] Delete the duplicate implementations in `c_api.cpp` and
  `assembly_loader.cpp`.
- [x] Withdraw the `O_NOFOLLOW` change; `project-io` moved to a storage
  platform abstraction and it no longer belongs in `read_json`.
- [x] Carry the version cascade and run the integrated Proof.

## Correction: the original severity was overstated

The 1.0.7.0 review asserted the danger was a stack overflow in the DOM
destructor, and that a `try`/`catch` therefore could not contain it. **That
mechanism does not hold for the pinned parser.** nlohmann 3.12.0 parses
iteratively *and* destroys iteratively: `json_value::destroy` flattens the
subtree into a heap-allocated `std::vector` before releasing it
(`include/nlohmann/json.hpp` around line 557).

Measured directly: with the depth guard disabled, a 200,000-deep checkpoint
document is parsed in full, destroyed without crashing, and then refused by
checkpoint contract validation with `invalid_project`. There is no crash to
prevent on this toolchain.

What remains real, and what this plan delivers:

- **Bounded work.** Unbounded depth still costs O(input) time and heap. The
  1.0.7.0 review's second finding described this accurately; the first
  overstated it as a crash.
- **One definition.** Three copies of the parser and two of the UTF-8
  validator, each with its own `= 64` constant, is a real drift hazard for a
  security-relevant limit.
- **Defense in depth.** The guard no longer depends on the parser's internal
  choice to destroy iteratively, which is not part of nlohmann's public
  contract.

The backlog called unit C "the only unit containing a real logic defect." That
label should be withdrawn. Unit C is hardening and deduplication.

## What the tests can and cannot prove

`tests/core/foundation/json_test.cpp` isolates the guard: it covers the exact
63/64 boundary, both overloads, malformed input, the UTF-8 accept and reject
table, and 200,000-deep documents. Disabling the guard fails it.

The `project-io` test deliberately claims less. A deeply nested checkpoint is
refused with or without the guard, because contract validation refuses it
anyway, so that test locks in the outcome rather than isolating the mechanism,
and says so in a comment.

## Withdrawn: the `O_NOFOLLOW` change

This plan originally added `O_NOFOLLOW` plus a regular-file check to
`read_json`, mirroring `read_artifact`. **That change is withdrawn.**

While this Task was in review, `main` gained a storage platform abstraction
(`ProjectStoragePlatform`, for OPFS in the browser). `project-io` no longer
opens files itself: `read_json` now calls `read_file_bytes(platform, path)`, and
`validate_managed_tree` is a platform method. A raw `::open(..., O_NOFOLLOW)`
would bypass that abstraction and break any non-POSIX backend.

Symlink semantics are now the platform implementation's concern. The hardening
should be applied inside the POSIX platform, next to `validate_managed_tree`,
which is a separate Task against a different module boundary.

Nothing is lost in the meantime: a symlink already present in a bundle is
refused by the recursive symlink scan that runs before any read. What
`O_NOFOLLOW` would have closed is only the window between that scan and the
open — a TOCTOU window, as the original core review correctly named it, not an
unguarded symlink. It was never assertable by a deterministic test, which is
why no test is lost with it.

## Deliberately not done

The CLI Host keeps its own `valid_utf8` and `parse_bounded_json`.
`tests/host/cli_test.py:807-811` asserts the CLI includes exactly
`lmdj/facade/application.hpp` and `lmdj/facade/assembly_loader.hpp`, enforcing
the `CLAUDE.md` invariant that Hosts use the Application Facade. Removing the
CLI's copies requires either widening that boundary or re-exporting the
functions through the Facade. Both are architecture decisions, and `CLAUDE.md`
forbids settling one inside an implementation Task. Recorded for a follow-up.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.11.0` | `1.0.13.0` | Runnable Assembly invalid-input behavior changes. |
| `foundation` | `0.1.0`, API 1 | `0.2.0`, API 1 | Adds public bounded parsing and UTF-8 validation; additive. |
| `authoring-domain` | `0.1.0` | `0.1.1` | Exact `foundation` dependency change only. |
| `project-cooker` | `0.2.0` | `0.2.1` | Exact dependency change only. |
| `project-io` | `0.3.0` | `0.3.1` | Bounded disk parsing; backward compatible. |
| `audio-runtime` | `0.3.0` | `0.3.1` | Exact dependency change only. |
| `provider-sdk` | `1.1.0` | `1.1.1` | Bounded disk parsing; backward compatible. |
| `application-facade` | `1.1.1` | `1.1.2` | Duplicates removed; behavior unchanged. |
| `core-cli` | `1.0.3` | `1.0.4` | Exact Facade dependency change only. |
| `core-mcp` | `1.1.0` | `1.1.1` | Exact Facade dependency change only. |
| `native-test-host` | `1.0.1` | `1.0.2` | Exact dependency change only. |
| Proof Providers | `1.0.1` | `1.0.2` | Exact `provider-sdk` change; source-package identity rehashed. |
| Contracts / Capabilities / Models | unchanged | unchanged | No Schema, wire, or persistence change. |

- Rebased onto the port-name Task, which took `1.0.12.0`; the module baselines
  above are therefore its numbers, not `main`'s at the time this was written.
- Compatibility: no Project migration. Documents already on disk are within the
  depth limit, and the limit only refuses input that contract validation would
  refuse anyway.
- Regenerate `products/lmdj/assembly.lock.json` after the Provider source
  edits; the declared Provider version is part of the hashed descriptor.
- Rollback reuses immutable Product Build `1.0.11.0`.
- No tag, Release, Channel promotion, or deployment is authorized.
