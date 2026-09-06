---
id: sanitizer-runtime-silent-start-failure
area: ci-release
status: open
recurrences:
  - date: 2026-09-06
    occurrence: https://github.com/endaye/lmdj/issues/693
    observed_by: Claude Fable 5.1 (Claude Code)
exit: none
---

# A sanitizer runtime that cannot start may die with no diagnostic at all, and a whole suite failing in a few milliseconds is that, not a test failure.

## Why

Sanitizer runtimes initialise before `main`. When the process layout they
need is unavailable, the honest ones print `FATAL: ThreadSanitizer: ...` and
exit; some print nothing. Measured on netcup (`6.8.0-137`, x86_64,
`vm.mmap_rnd_bits=32`, under `LockPersonality=yes`), ten starts each of a
minimal two-thread program:

| runtime | ran | FATAL with message | died silently |
| --- | ---: | ---: | ---: |
| GCC 13.3 `libtsan` | 0 | 10 | 0 |
| clang-18 `libclang_rt.tsan.so` | 1 | 0 | 9 |
| clang-22 `libclang_rt.tsan.so` | 0 | 10 | 0 |

The clang-18 row is the "10/11 tests fail in 0.01 s with no diagnostic" that
#676 probe B″ recorded as unexplained, and the one success is why a single
run can mislead: with 32 bits of mmap entropy, whether the layout happens to
fit is random per process. With `vm.mmap_rnd_bits=28` all three rows are
10/10. None of this is visible from the product code, the test, or CTest's
output, which reports only the exit code and an empty log.

Two further facts shape any fix. Static Clang sanitizer runtimes are linked
whole-archive and their C++ half defines global `operator new`/`delete`, so
a test that replaces those operators cannot link against them
(`multiple definition`); the runtime must be shared. And a runtime that
recovers by re-executing itself with `ADDR_NO_RANDOMIZE` cannot do so under
`LockPersonality=true` — LLVM 22 then reports `unable to disable ASLR
(perhaps sandboxing is enabled?)` or `memory layout is incompatible, even
though ASLR is disabled`. Upgrading the compiler cannot fix a layout the
kernel hands out; only the host can.

## How to apply

When every test of a sanitizer tier fails in well under a second, or a
sanitizer suite fails with an empty log, do not read it as a test failure and
do not rerun it expecting a different answer. Compile a minimal two-thread
program with the same compiler and `-fsanitize=` flags, run it ten times under
the runner unit's hardening (`systemd-run -p LockPersonality=yes ...`), and
count ran / FATAL / silent. If the runtime does not start, the fix is host
state — `scripts/ci/host/configure-sanitizer-aslr.sh` on a `ci-core` host —
recorded as an operator decision, never a test edit or a compiler swap alone.
Keep the compiler pin single-sourced in
`scripts/ci/host/install-llvm-toolchain.sh` so the probe and the lane agree
on which runtime is under test.

No gate exists yet: the invariant is settled but violation is not
mechanically decidable from a CI run — an empty log with a fast exit is
indistinguishable from a test that crashed on its first assertion without
running the minimal probe, which needs the host.
