---
id: asan-macos-fork-child-stack-depot-boundary
area: core
status: open
recurrences:
  - date: 2026-10-01
    occurrence: https://github.com/endaye/lmdj/pull/1749
    observed_by: Claude Opus 5.5
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
  - It is this pitfall when the report says `crashed on child side of fork pre-exec`, and its stack runs `libSystem_atfork_child` → `calloc` → ASan `StackDepot`/`StackStore` `Create` → `_os_unfair_lock_lock_slow`.
- **Confirm it.** Call `__asan_print_accumulated_stats()` (from `<sanitizer/asan_interface.h>`) just before the `fork()`. The depot's id count should sit a few ids below a multiple of 65 536. Then compare the failure rate of `main`'s binary and the head's binary under the same `TMPDIR`.
- **Do not hide it:**
  - do not reorder or remove allocations to move the count;
  - do not set `malloc_context_size=0`;
  - do not skip the test under macOS ASan;
  - do not treat the failure as a product defect.
- **Record it.** Add the recurrence here, state the `TMPDIR` the `core_macos` evidence ran under, and link #1752.

The exit is #1752: the crash children re-exec the test binary instead of continuing after a bare `fork()`, and a deterministic source check keeps new bare forks out. No eligible mechanism exists until then, because no test-side call can tell how close the depot is to its next boundary.
