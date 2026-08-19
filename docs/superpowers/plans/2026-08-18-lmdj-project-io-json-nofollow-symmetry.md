# LMDJ Project-IO JSON Symlink Symmetry Implementation Plan

**Goal:** Close machine task C4 — "Give `project_store.cpp`'s JSON read
paths the `O_NOFOLLOW` symmetry `read_artifact()` already has" — by
verifying the symmetry already delivered by the storage platform
migration, locking it in with the missing file-level test, and recording
the finding against the task list.

Origin: `docs/quality/2026-08-17-machine-task-todo.md` task C4, which
carries `docs/quality/2026-08-03-review-backlog.md` unit C2 forward from
`docs/quality/2026-08-01-core-review.md` finding 3.

## Premise check: the asymmetry no longer exists

The 2026-08-01 review described `read_json()` opening JSON files with a
symlink-following `ifstream` while `read_artifact()` used
`openat(O_NOFOLLOW)`. That code shape is gone. Verified on `main` at
`fbf263e`:

- Every JSON read routes through `read_json()` →
  `read_file_bytes()` → `ProjectStoragePlatform::read_complete()`
  (`packages/project-io/src/project_store.cpp:161-198`) — the same call
  `read_artifact()` makes at `project_store.cpp:3147`.
- The native `read_complete()` opens via `open_regular_file()`
  (`packages/project-io/src/native/storage_platform.cpp:2304-2313`):
  parent directories walked symlink-free with `openat(O_DIRECTORY |
  O_NOFOLLOW)`, final component opened `O_NOFOLLOW`, `ELOOP` mapped to
  `invalid_project`. `read_artifact()` gains nothing that `read_json()`
  lacks; they share one implementation.
- The web platform reads OPFS, which has no symbolic links.
- Bundle entry points additionally run `validate_managed_bundle_tree()`
  before any read, and the staging-marker reads at
  `project_store.cpp:1568` and `:1656` sit behind
  `validate_managed_tree()` calls (`:1537`, `:1621`).

This is the outcome the 2026-08-03 input-hardening plan prescribed when
it **withdrew** the in-`read_json` `O_NOFOLLOW` edit: the guard belongs
in the POSIX platform, not in `project_store.cpp`, and it now lives
exactly there. Implementing C4 literally — a raw `::open(O_NOFOLLOW)`
inside `project_store.cpp` — would reintroduce what was withdrawn and
break the non-POSIX backend.

## Tasks

- [ ] Add `test_json_reads_reject_symlinked_files`, the file-level
  complement of `test_symlinked_managed_directory_is_rejected_before_recovery`
  and of `read_artifact`'s
  `test_artifact_reads_are_bounded_symlink_safe_and_integrity_verified`:
  a valid bundle, then `manifest.json` (and the head checkpoint)
  replaced by symlinks to an external file, asserting `load()` refuses
  with `invalid_project` and the external file survives untouched.
- [ ] Record the verification in
  `docs/quality/2026-08-18-project-io-json-symlink-symmetry.md` with the
  evidence above, in the style of the C1 measurement record.
- [ ] Strike C4 from `docs/quality/2026-08-17-machine-task-todo.md` with
  the outcome and the record reference.
- [ ] Refresh the stale comment in
  `tests/core/project_io/project_store_test.cpp` (the
  `test_json_reads_reject_excessive_nesting` preamble) so it points at
  the file-level symlink tests instead of saying the module does not
  assert symlink handling.

## What the tests can and cannot prove

The new test locks the observable contract — a symlinked JSON file is
refused before any content is trusted — end to end through `load()`,
which is the same claim level `read_artifact`'s symlink test makes. The
platform-level mechanism (`ELOOP` mapping) is already isolated in
`tests/core/project_io/storage_platform_contract_test.cpp:1023`. The
scan-to-open TOCTOU window remains untestable deterministically, exactly
as the 2026-08-03 withdrawal record stated; the window is identical for
JSON and artifact reads, so no asymmetry is left open.

## Version Management

Canonical policy: `docs/governance/version-management.md`.

| Domain | Current | Target | Reason |
| --- | --- | --- | --- |
| Product Build | `1.0.23.0` | unchanged | No runtime behavior change: no production source is edited. |
| `project-io` | current `main` value | unchanged | Test and documentation only; no API or behavior change. |
| Contracts / Capabilities / Models | unchanged | unchanged | No Schema, wire, or persistence change. |

Version impact: none — the change adds a test and documentation; module
manifests, the Assembly, and `assembly.lock.json` are untouched.

## Documentation impact

`docs/quality/2026-08-18-project-io-json-symlink-symmetry.md` (new) and
`docs/quality/2026-08-17-machine-task-todo.md` (C4 row) are quality
working lists, not portal-managed architecture pages; the portal derives
module identity from manifests, which do not change. No portal route is
affected.
