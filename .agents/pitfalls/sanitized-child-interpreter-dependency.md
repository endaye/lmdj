---
id: sanitized-child-interpreter-dependency
area: ci-release
status: open
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34272435905
    observed_by: Codex
exit: none
---

# A process-isolation test cannot assume its parent interpreter starts without the parent's loader environment.

## Why

The runtime tests introduced in #1017 passed on the local system Python but
failed on CI's relocated setup-python installation. Even sleep/output fixtures
returned runtime_failure and emitted no observation file after the test removed
the environment. The runner log names a tool-cache Python and its explicit
LD_LIBRARY_PATH. [setup-python's source](https://github.com/actions/setup-python/blob/main/src/find-python.ts)
adds that library path on Linux; it is not part of the model executor's intended
environment. This supports a loader-dependency diagnosis, but the deliberately
discarded raw child stderr does not prove the exact remote loader error.

Testing on a system installation concealed the interpreter prerequisite. Passing
the whole environment back to a child would undermine the property being tested.

## How to apply

Probe candidate fixture interpreters with the exact sanitized environment and a
fixed stdlib response before using their shebangs. Fail with a concrete prerequisite
message when none runs; do not silently skip process tests or weaken the production
allowlist. Keep synthetic dependency probes distinct from actual CI evidence.
The current partial mechanism is `standalone_python` in
`tests/build/ci_canary_assessment_runtime_test.py`; inspect that helper before
adding another suite-specific probe.

`exit: none`: the focused test helper verifies this suite's child interpreter,
not every subprocess fixture in the repository. Remote acceptance of the repair
still needs the next exact main ci_contract execution.
