---
id: tsan-runner-runtime-compatibility
area: ci-release
status: absorbed
recurrences:
  - date: 2026-08-05
    occurrence: https://github.com/endaye/lmdj/commit/f2947cecaee1c75a8659e6a4f64aa69d1a29a265
    observed_by: unknown
exit: gate:tests/build/ci_nightly_workflow_test.py
---

# A TSan build succeeding on a runner does not prove that the runner can execute the TSan runtime.

## Why

The first Contabo Nightly migration configured and built the TSan preset, then
failed at runtime with `ThreadSanitizer: unexpected memory mapping`. Runner
registration, selection and compilation therefore cannot establish TSan
compatibility; only the same test command reaching a successful terminal job
on the named runner can do so.

## How to apply

Accept a TSan routing change only from same-revision evidence: the expected
`runner_name` and a successful job running the fixture, dependency, configure,
build and stress commands on the target role. That evidence arrived on
2026-09-06 (#693) once the host prerequisite was understood — the 6.8 kernel's
32-bit `vm.mmap_rnd_bits`, capped to 28 by
`scripts/ci/host/configure-sanitizer-aslr.sh` — and scheduled TSan moved to
`ci-core`. The exit gate now fixes that route, requires the lane to verify the
sysctl before it builds, and forbids a second TSan lane, so a host that
regresses fails naming its remedy rather than reproducing the original
mystery. See also
[`sanitizer-runtime-silent-start-failure`](sanitizer-runtime-silent-start-failure.md)
for how to tell a runtime that cannot start from a test that failed.
