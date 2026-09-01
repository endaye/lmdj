---
id: coverage-floor-tuning
area: core
status: absorbed
recurrences:
  - date: 2026-08-18
    occurrence: https://github.com/endaye/lmdj/pull/188
    observed_by: unknown
  - date: 2026-08-19
    occurrence: https://github.com/endaye/lmdj/pull/190
    observed_by: unknown
  - date: 2026-09-01
    occurrence: https://github.com/endaye/lmdj/pull/518
    observed_by: Codex GPT-5
exit: skill:.agents/skills/issue-done/SKILL.md
---

# A red coverage gate is an instrument reading, not a target: raise real coverage, and never lower a floor to make CI green.

## Why

When the Application Facade coverage gate went red, the available moves were to
lower the floor or to write the missing tests. #188 took the second: behavioral
tests for previously unexercised failure semantics moved the package from
84.04% to 86.28%. Only then did #190 ratchet the floor from 84% to 85% — the
correct direction, locking in a gain that already existed, and it withdrew a
finding that had argued otherwise.

`docs/quality/core-test-policy.md` states the rule directly: floors "may rise
after sustained behavioral coverage lands. They must not be lowered merely to
make CI green." Whether a proposed change is a legitimate re-measurement or a
convenience edit is a judgment call, so this exits to guidance rather than to a
gate — the floor file is itself the gate, and lowering it is editing the gate.

## How to apply

When a coverage gate blocks a Task, first ask which behavior is untested and
why, and distinguish hard-to-test from simply-untested. Write behavioral tests
for unreached failure semantics; do not chase green lines. Raise a floor only
after the coverage it asserts is already sustained, and keep the floor outside
the measured run-to-run variance band — `2026-08-18-facade-coverage-gate-measurement.md`
records about ±4 lines for this package. A toolchain or source-topology change
that invalidates a floor requires a reviewed measurement and a policy update,
never an ad hoc threshold edit.
