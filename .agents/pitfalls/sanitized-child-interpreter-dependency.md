---
id: sanitized-child-interpreter-dependency
area: ci-release
status: absorbed
recurrences:
  - date: 2026-09-08
    occurrence: https://github.com/endaye/lmdj/actions/runs/34272435905
    observed_by: Codex
  - date: 2026-09-19
    occurrence: https://github.com/endaye/lmdj/actions/runs/35419357786
    observed_by: Claude Code (Fable 5.1)
  - date: 2026-09-26
    occurrence: https://github.com/endaye/lmdj/issues/1551
    observed_by: Codex
exit: gate:tests/build/ci_system_python_test.py
escalation: https://github.com/endaye/lmdj/issues/1551
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
The shared mechanism is `tests/build/release_fixture_interpreter.py`:
`standalone_python` is the probe, `fixture_python()` the verified interpreter
for direct spawns and shebangs, `fixture_path()` a PATH whose `python3` is
that interpreter for production vectors resolved by name, and
`reexec_when_parent_cannot_start_sanitized()` for tests of production tools
that spawn `sys.executable` themselves. Use it instead of `os.environ["PATH"]`
or `sys.executable` wherever a child runs under the sanitized environment.

Second recurrence (2026-09-19): the release tooling suites added after the
first repair passed `os.environ["PATH"]` and `sys.executable` straight into the
sanitized executor and failed 66 of 67 `core (ubuntu)` tests with `exited 127`
on every netcup runner once the toolcache carried 3.11.16; the 185-byte child
output matched the loader message exactly. The fixture repair protects tests
only; `release-audit.yml` runs the same production spawns on the same runners,
so the exit is the host-level toolcache repair tracked in
[#1551](https://github.com/endaye/lmdj/issues/1551).

The 2026-09-26 repair selects `/usr/bin/python3` for Linux Core (including
package, ASan, coverage, TSan and benchmark), Deploy contract and release-audit.
`scripts/ci/host/select-system-python.sh` requires Python 3.11+ and verifies
both startup by name and a `sys.executable` child without loader variables
before publishing the job-local Python PATH. Failure requires host repair,
not an expanded production environment allowlist. The exit test exercises
successful isolated spawns, rejects a loader-dependent interpreter, and pins
all eight consuming jobs to the prerequisite. Existing fixture probes remain
necessary for other environments. Actual post-change run acceptance is retained
on #1551 separately; absorption identifies the enforcing mechanism and does not
claim those remote jobs have already passed.
