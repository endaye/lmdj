---
id: asan-macos-fork-child-stack-depot-boundary
area: core
status: open
recurrences:
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1749
    observed_by: Claude Opus 5.5
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1756
    observed_by: Claude Opus 5.5
  - date: 2026-10-02
    occurrence: https://github.com/endaye/lmdj/pull/1766
    observed_by: Claude Code (Opus 5.5)
  - date: 2026-10-04
    occurrence: https://github.com/endaye/lmdj/issues/1815
    observed_by: Codex
exit: none
escalation: https://github.com/endaye/lmdj/issues/1752
---

# Under macOS ASan, a test that forks without exec can lose its child to SIGKILL inside `fork()` when the parent's ASan stack depot is just short of a growth boundary.

## Why

Before control returns from `fork()`, libSystem runs its own child handlers (`_notify_fork_child`, `_libcoreservices_fork_child`), and they allocate. The stacks of those allocations are new to the child, so ASan stores them. If the parent sat a few ids short of a depot node chunk (65 536 ids) or a `StackStore` block (8 MiB), storing them creates the next chunk. Creation takes a lock the child cannot own, and libplatform aborts with `os_unfair_lock is corrupt`. The child dies before any test code runs.

Whether a binary sits in that window depends on how many allocation call sites the build has and on string lengths such as `TMPDIR`. A change can therefore turn the lane red with no defect in the code under test. On #1749, moving `ProjectState` copies to the heap shifted two binaries into the window. Under `TMPDIR=/private/tmp/lmdjt` their children died in 11 of 16 runs, against 0 of 16 on `main`. Under the macOS default `TMPDIR` the head passed. Product code does not fork.

## How to apply

- **Recognise it.** A fork-based test fails `core_macos` with a child that did not exit (`WIFEXITED` false), and passes on Linux `core_asan`.
  - Open the newest `~/Library/Logs/DiagnosticReports/<test binary>-*.ips`.
  - It is this pitfall when the report says `crashed on child side of fork pre-exec` and `os_unfair_lock is corrupt`, and its stack runs from `libSystem_atfork_child`, through any one of its child handlers (`_notify_fork_child`, `_libcoreservices_fork_child`, `_objc_atfork_child`, …) and an ASan-intercepted allocation or free (`calloc`, `free`, …), into an ASan `StackDepot`/`StackStore` `Create`, then `_os_unfair_lock_lock_slow`. Which handler and which call appear varies between runs.
- **Confirm it.** Call `__asan_print_accumulated_stats()` (from `<sanitizer/asan_interface.h>`) just before the `fork()`. The depot's id count should sit a few ids below a multiple of 65 536. Then compare the failure rate of `main`'s binary and the head's binary under the same `TMPDIR`. A control `TMPDIR` must keep the failing path's length: a fresh directory of another length moves the depot count too, so its pass cannot separate this cause from any other.
- **Do not hide it:**
  - do not reorder or remove allocations to move the count;
  - do not set `malloc_context_size=0`;
  - do not skip the test under macOS ASan;
  - do not treat the failure as a product defect.
- **Record it.** Add the recurrence here, state the `TMPDIR` the `core_macos` evidence ran under, and link #1752.

Second recurrence (#1756). Same mechanism, a different handler: `libSystem_atfork_child` → `_objc_atfork_child` → `free` → ASan `StackDepot` `TwoLevelMap::Create`. It happened under `TMPDIR=/private/tmp/lmdjt`, in a PR that changes no allocation site. `lmdj_project_io_candidate_adoption_tests` links only Project I/O and its dependencies (Authoring Domain, Foundation, picosha2, nlohmann_json). The PR changed none of them, so its binary is the one `main` builds since #1749. So a fork-child SIGKILL in `core_macos` says nothing about the PR under test, only about where the depot count landed in that build.

Third recurrence (#1766). `project_io.candidate_adoption` failed under `TMPDIR=/private/tmp/lmdjt` (18 characters): 3 of 5 runs on main's base `738a3e48`, and 4 of 5 on the PR head, whose change does not touch Project I/O's link set. It passed under the default `TMPDIR`, and under fresh directories of 28 and 29 characters. The author first blamed concurrent sessions sharing that directory, but every passing control also changed the path length, which this mechanism already explains. On main `724576f8` the binary passed 25 of 25 runs under 18- and 30-character paths, outside the window, so the two causes could not be separated afterwards. The passing core_macos evidence ran under `TMPDIR=/private/tmp/lmdjt-pe`.

The exit is [#1752](https://github.com/endaye/lmdj/issues/1752), its escalation Issue: the crash children re-exec the test binary instead of continuing after a bare `fork()`, and a deterministic source check keeps new bare forks out. No eligible mechanism exists until then, because no test-side call can tell how close the depot is to its next boundary.

Fourth recurrence (#1815). The retained 2026-10-04 23:22:24 crash report
for `lmdj_facade_candidate_store_tests` identifies `retry_finishes_during_adoption`
line 101 → `fork` → `_notify_fork_child` → intercepted `calloc` →
`StackDepotBase::Put` → `TwoLevelMap::Create` → corrupt unfair lock / SIGKILL.
This accounts for the parent's ready-pipe EOF; no AF_UNIX endpoint exists in
the Candidate Store path. A different TMPDIR changes allocations and does not
prove a socket-path overflow. #1815 replaces all eleven bare spawn sites in
this one test file with fresh `posix_spawn` roles, retaining the same hooks,
pipes, crash boundaries, and parent-side assertions. The remaining six files
and global source guard remain the scope of #1752; this partial repair does
not absorb that repository-wide pitfall.
