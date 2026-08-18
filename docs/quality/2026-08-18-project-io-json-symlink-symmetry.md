# Project-IO JSON Symlink Symmetry — C4 Verification Record (2026-08-18)

Machine task C4
([`2026-08-17-machine-task-todo.md`](2026-08-17-machine-task-todo.md), from
the 2026-08-03 backlog unit C2, from
[`2026-08-01-core-review.md`](2026-08-01-core-review.md) finding 3) asked
for "`project_store.cpp`'s JSON read paths" to gain "the `O_NOFOLLOW`
symmetry `read_artifact()` already has". **The asymmetry the task
describes no longer exists.** No production source needed to change;
what was missing is a test that locks the symmetry in, and this record.

## Evidence, against `main` at `fbf263e`

- Every JSON read routes through `read_json()` → `read_file_bytes()` →
  `ProjectStoragePlatform::read_complete()`
  (`packages/project-io/src/project_store.cpp:161-198`) — the identical
  call `read_artifact()` makes at `project_store.cpp:3147`. There is one
  read implementation; two entry points.
- The native `read_complete()` opens through `open_regular_file()`
  (`packages/project-io/src/native/storage_platform.cpp:2304-2313`):
  parent directories walked symlink-free with
  `openat(O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)`, the final component
  opened `O_NOFOLLOW`, and `ELOOP` mapped to `invalid_project`.
- The web platform reads OPFS, which has no symbolic links.
- Bundle entry points run `validate_managed_bundle_tree()` — the
  recursive symlink scan — before any read, and the staging-marker reads
  at `project_store.cpp:1568` and `:1656` sit behind
  `validate_managed_tree()` calls (`:1537`, `:1621`).

This is exactly the placement the 2026-08-03 input-hardening plan
prescribed when it **withdrew** the in-`read_json` `O_NOFOLLOW` edit
during review: the guard belongs inside the POSIX platform, next to
`validate_managed_tree`, because `project_store.cpp` must stay
backend-neutral
([plan, "Withdrawn: the `O_NOFOLLOW` change"](../superpowers/plans/2026-08-03-lmdj-foundation-input-hardening.md)).
Implementing C4 literally today — a raw `::open(..., O_NOFOLLOW)` inside
`project_store.cpp` — would reintroduce what was withdrawn and break the
non-POSIX backend.

## What was still missing, and is now added

`read_artifact` had a file-level symlink test
(`test_artifact_reads_are_bounded_symlink_safe_and_integrity_verified`)
and `read_complete` had a platform-contract one
(`storage_platform_contract_test.cpp`:
`test_symlinks_are_rejected_and_system_failures_are_typed`), but no test
drove a symlinked JSON file through a public `ProjectStore` entry.

`test_json_reads_reject_symlinked_files` now does: with a valid bundle,
replacing `manifest.json` and then `history/checkpoints/0.json` with
symlinks to an external file makes `load()` fail with `invalid_project`,
the external file survives untouched, and restoring real files makes
`load()` succeed again. The stale comment on
`test_json_reads_reject_excessive_nesting` — which said symlink handling
was *not* asserted in this module — now points at the new test.

## Scope of the claim

The observable contract (a symlinked JSON file is refused before any
content is trusted) is locked end to end through `load()`. The
platform-level mechanism is isolated in the storage platform contract
test. The scan-to-open TOCTOU window remains deterministically
untestable, as the 2026-08-03 withdrawal record already stated — and it
is now identical for JSON and artifact reads, since they share one
`read_complete()`. No asymmetry is left open.

## Outcome

C4 is **closed by verification**: the requested symmetry exists at the
platform layer where the withdrawn 2026-08-03 plan deliberately placed
it, and the file-level test gap is filled. Implementation plan:
[`2026-08-18-lmdj-project-io-json-nofollow-symmetry.md`](../superpowers/plans/2026-08-18-lmdj-project-io-json-nofollow-symmetry.md).

Verification run 2026-08-19, worktree `fix/project-io-json-symlink-symmetry`:
`lmdj_project_store_tests`, `lmdj_project_storage_platform_tests`,
`lmdj_project_io_fault_matrix_tests`, `lmdj_take_journal_tests`,
`lmdj_project_bundle_transfer_tests` — all PASS.
