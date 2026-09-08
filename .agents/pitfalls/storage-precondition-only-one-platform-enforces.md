---
id: storage-precondition-only-one-platform-enforces
area: web-host
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/issues/902
    observed_by: Claude Code (Opus 5)
exit: none
---

# A ProjectStoragePlatform precondition that only the Web implementation enforces makes a whole green native suite meaningless

## Why

`ProjectStoragePlatform` has two implementations with very different powers.
The native one publishes a directory with `renameat2(RENAME_NOREPLACE)`: one
atomic syscall that needs no lock, no intent record and no recovery. The OPFS
one cannot rename, so it publishes by copying under a pending
`lmdj.storage.directory-publication.v1` intent, and that emulation only works
if the caller holds a writer lease on the *destination* — the lease is both the
exclusion and the trigger that recovers an interrupted copy.

So the Web implementation carries preconditions the native one silently does
not need. A Core call site written and tested against native satisfies the
interface, passes every native test, and fails only in a browser. In #902 the
Sound Set Store leased its staging directory and released it before
publishing; native did not care, the whole `soundset_store_test.cpp` suite was
green, and no Sound Set could be installed from a browser at all. The refusal
surfaced as a bare `IO_ERROR` because `storage_condition: invalid_state` is not
public vocabulary the Facade forwards, so the symptom named nothing.

None of this is visible from the interface. `storage_platform.hpp` declares
`publish_directory_if_absent` with two paths and no stated precondition, and
the only correct call site — `ProjectBundleTransfer::commit` — satisfies it
incidentally, so reading it teaches nothing either. The defect is in the
coverage plan, not in the product logic: Stage 11 Task 2's test list named only
native tests for a module whose whole job is writing through the storage
platform.

## How to apply

- When a Core module gains a code path that **writes** through
  `ProjectStoragePlatform` — `acquire_writer`, `create_immutable`,
  `replace_complete`, `append_durable`, `publish_directory_if_absent` — its
  Task must include a leg on the Web platform, not only native. The harness
  already exists: add an `action=` to
  `tests/platform/web/project_io/project_io_web_test.cpp` and drive it from
  `project_io_web_conformance.spec.mjs`. It runs the real Core code compiled to
  wasm against real OPFS and needs no Host, no fetch and no Creator build.
- Before writing such a path, read what the OPFS implementation demands in
  `packages/project-io/src/web/library_opfs_storage.js` — `activeLease`,
  `coveringLease` and `recoverIntents` are where the unstated preconditions
  live — and copy the discipline of the nearest existing correct caller rather
  than the nearest convenient one.
- When you discover a precondition only one platform enforces, write it onto
  the interface declaration in `storage_platform.hpp` in the same commit.
  Including *when* it must be satisfied: a lease acquired after the caller has
  already inspected the destination is too late, because recovery runs at
  acquisition.
- A bare `IO_ERROR` with no `details.reason` from a storage path is a signal,
  not noise: it means the refusal came from the platform rather than from a
  named Core check. Read `details.storage_condition` at the Core boundary
  before it is dropped, rather than guessing from the public refusal.
