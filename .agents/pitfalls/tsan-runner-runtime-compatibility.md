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

Keep scheduled TSan on its accepted Hosted runner while a manual dispatch runs
the same fixture, dependency, configure, build and stress commands on
`ci-core`. Accept a routing change only from same-revision evidence containing
the expected `runner_name` and a successful probe job. The exit gate fixes both
routes and their command parity so the probe cannot silently become an easier
test.
